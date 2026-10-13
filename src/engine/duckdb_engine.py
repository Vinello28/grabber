"""
DuckDB Analytical Query Engine.
Handles out-of-core streaming SQL, memory boundaries, disk spillover,
and dynamic view registration.
"""

from __future__ import annotations

import contextlib
import logging
import os
import sys
import time
from collections.abc import Callable
from pathlib import Path
from types import TracebackType
from typing import Any

if sys.version_info >= (3, 11):
    from typing import Self
else:
    from typing_extensions import Self

import duckdb

from src.adapters.csv_adapter import CsvAdapter
from src.adapters.detector import DatasetDetector
from src.adapters.parquet_adapter import ParquetAdapter
from src.adapters.xml_adapter import XmlAdapter
from src.core.interfaces import IQueryEngine
from src.core.models import (
    ColumnMeta,
    DatasetSchema,
    DataType,
    QueryResult,
    QuerySpec,
)
from src.core.paths import get_spill_dir
from src.engine.query_builder import QueryBuilder
from src.engine.resource_monitor import ResourceMonitor

logger = logging.getLogger(__name__)


class DuckDBEngine(IQueryEngine):
    """Execution engine for big data analytics using DuckDB."""

    def __init__(
        self,
        memory_limit: str | None = None,
        threads: int | None = None,
        temp_dir: str | None = None,
    ):
        self.temp_dir = Path(temp_dir).resolve() if temp_dir else get_spill_dir()
        self.instance_spill_dir = self.temp_dir / f"session_{os.getpid()}_{id(self)}"
        self.instance_spill_dir.mkdir(parents=True, exist_ok=True)

        self.memory_limit = memory_limit or ResourceMonitor.calculate_safe_memory_limit()
        self.threads = threads or (os.cpu_count() or 4)

        self.conn = duckdb.connect(database=":memory:")
        self._configure_connection()

        self.current_schema: DatasetSchema | None = None
        self.current_view_name = "current_dataset"
        self.current_dataset_path: str | None = None
        self._current_files: list[str] = []
        self.current_sql_source: str | None = None

        # Caches for query execution and metadata
        self._count_cache: dict[str, int] = {}
        self._distinct_cache: dict[tuple[str, str, int], list[Any]] = {}

        # Materialized temporary query table for instant sub-millisecond pagination
        self._active_query_cache_table = "_active_query_cache"
        self._active_query_fingerprint: str | None = None
        self._active_query_total_count: int | None = None

        # Adapters
        self.csv_adapter = CsvAdapter()
        self.parquet_adapter = ParquetAdapter()
        self.xml_adapter = XmlAdapter()

    def _is_parallel_csv_conflict_error(self, e: Exception) -> bool:
        msg = str(e).lower()
        return "parallel scanner does not support null_padding" in msg or "disable the parallel csv reader with parallel=false" in msg

    def _is_missing_parquet_cache_error(self, e: Exception) -> bool:
        msg = str(e).lower()
        return ("no files found that match the pattern" in msg and "parquet" in msg) or (
            "io error" in msg and ".parquet" in msg
        )

    def _fallback_csv_to_sequential_if_needed(self, e: Exception) -> bool:
        if not self._is_parallel_csv_conflict_error(e):
            return False
        if not self.current_schema or self.current_schema.source_format != "csv":
            return False
        if getattr(self.csv_adapter, "parallel", None) is False:
            return False
        logger.warning(
            "Conflitto scanner CSV parallelo rilevato con null_padding e newline quotate: "
            "fallback automatico a parallel=false per %s",
            self.current_dataset_path,
        )
        self.csv_adapter.parallel = False
        files = getattr(self, "_current_files", None) or self.current_dataset_path
        self.current_sql_source = self.csv_adapter.build_sql_source(files, parallel=False)
        self.conn.execute(
            f"CREATE OR REPLACE VIEW {self.current_view_name} AS SELECT * FROM {self.current_sql_source}"
        )
        return True

    def _fallback_missing_parquet_cache_if_needed(self, e: Exception) -> bool:
        if not self._is_missing_parquet_cache_error(e):
            return False
        if not self.current_dataset_path:
            return False
        logger.warning(
            "Cache Parquet non più accessibile su disco (%s): fallback automatico a sorgente originale %s",
            e,
            self.current_dataset_path,
        )
        self.clear_query_cache()
        self.connect_dataset(self.current_dataset_path)
        return True

    def _execute_sql(self, sql: str) -> duckdb.DuckDBPyConnection:
        """Execute SQL with transparent fallback to sequential CSV reader or original dataset source."""
        try:
            return self.conn.execute(sql)
        except Exception as e:
            if self._fallback_csv_to_sequential_if_needed(e):
                return self.conn.execute(sql)
            if self._fallback_missing_parquet_cache_if_needed(e):
                return self.conn.execute(sql)
            raise

    def _configure_connection(self) -> None:
        """Apply performance and memory safety pragmas."""
        self.conn.execute(f"PRAGMA max_memory='{self.memory_limit}'")
        self.conn.execute(f"PRAGMA threads={self.threads}")
        safe_temp_dir = str(self.instance_spill_dir).replace("'", "''")
        self.conn.execute(f"PRAGMA temp_directory='{safe_temp_dir}'")
        self.conn.execute("PRAGMA preserve_insertion_order=false")
        self.conn.execute("PRAGMA parquet_metadata_cache=true")
        self.conn.execute("PRAGMA enable_external_file_cache=true")
        self.conn.execute("PRAGMA allocator_background_threads=true")
        self.conn.execute("PRAGMA allocator_flush_threshold='128MB'")


    def has_active_view(self) -> bool:
        """Check if current_dataset table/view exists in DuckDB catalog and is actively queryable."""
        try:
            res = self.conn.execute(
                "SELECT 1 FROM information_schema.tables WHERE table_name = ?",
                [self.current_view_name],
            ).fetchone()
            if not res:
                return False
            # Probe underlying files to ensure physical existence
            self.conn.execute(f"SELECT 1 FROM {self.current_view_name} LIMIT 0")
            return True
        except Exception:
            return False

    def ensure_view_exists(self) -> None:
        """Ensure current_dataset view exists and is queryable, recreating or falling back if necessary."""
        if self.current_sql_source is None:
            if self.current_schema and self.current_schema.source_format == "xml":
                raise RuntimeError(
                    "Il dataset XML non è ancora indicizzato in cache Parquet. "
                    "Fai clic su '⚡ Indicizza XML in Parquet' nella barra laterale per abilitare le interrogazioni."
                )
            if self.current_dataset_path:
                self.connect_dataset(self.current_dataset_path)
                if self.current_sql_source is None:
                    raise RuntimeError(
                        f"Impossibile creare una vista SQL per il dataset: {self.current_dataset_path}"
                    )
                return
            raise RuntimeError(
                "Nessun dataset attivo caricato nel motore. Seleziona e carica un dataset prima di eseguire query."
            )

        if self.has_active_view():
            return

        # If view does not exist or physical files are missing, attempt reconnect to original source
        if self.current_dataset_path:
            self.connect_dataset(self.current_dataset_path)
            if self.has_active_view():
                return

        if self.current_sql_source:
            self.conn.execute(
                f"CREATE OR REPLACE VIEW {self.current_view_name} AS SELECT * FROM {self.current_sql_source}"
            )
            return

        raise RuntimeError(
            "Nessun dataset attivo caricato nel motore. Seleziona e carica un dataset prima di eseguire query."
        )

    def clear_query_cache(self) -> None:
        """Clear active query materialized table and fingerprint."""
        self._active_query_fingerprint = None
        self._active_query_total_count = None
        if hasattr(self, "conn") and self.conn:
            with contextlib.suppress(Exception):
                self.conn.execute(f"DROP TABLE IF EXISTS {self._active_query_cache_table}")
        import gc
        gc.collect()

    def connect_dataset(self, path: str) -> DatasetSchema:
        """
        Analyze path, select adapter, inspect schema, and register
        a streaming view without loading full data into RAM.
        """
        analysis = DatasetDetector.analyze_path(path)
        fmt = analysis["format"]
        files = analysis["files"]
        self.current_dataset_path = path
        self._current_files = files
        self.clear_query_cache()
        self._count_cache.clear()
        self._distinct_cache.clear()
        with contextlib.suppress(Exception):
            self.conn.execute("CHECKPOINT")
        import gc
        gc.collect()

        if fmt == "csv":
            self.csv_adapter.parallel = None
            cache_path = self.csv_adapter.get_cache_path(files)
            if cache_path.exists() and any(cache_path.glob("**/*.parquet")):
                safe_cache = str(cache_path.resolve()).replace("'", "''")
                sql_source = f"read_parquet('{safe_cache}/**/*.parquet', union_by_name=true)"
                self.current_schema = self.csv_adapter.inspect_schema(files, self.conn)
            else:
                self.current_schema = self.csv_adapter.inspect_schema(files, self.conn)
                sql_source = self.csv_adapter.build_sql_source(files)
        elif fmt == "parquet":
            self.current_schema = self.parquet_adapter.inspect_schema(files, self.conn)
            sql_source = self.parquet_adapter.build_sql_source(files)
        elif fmt == "xml":
            self.current_schema = self.xml_adapter.inspect_schema(files, self.conn)
            cache_path = self.xml_adapter.get_cache_path(files)
            if cache_path.exists() and any(cache_path.glob("**/*.parquet")):
                sql_source = f"read_parquet('{cache_path!s}/**/*.parquet', union_by_name=true)"
            else:
                # Store files on schema for potential conversion
                sql_source = None
        else:
            raise ValueError(f"Unsupported format '{fmt}' in path: {path}")

        self.current_sql_source = sql_source

        # Ensure schema source_path and stats strictly reflect the requested path
        self.current_schema.source_path = path
        self.current_schema.file_count = len(files)
        self.current_schema.total_size_bytes = analysis["total_size_bytes"]

        if sql_source:
            self.conn.execute(f"CREATE OR REPLACE VIEW {self.current_view_name} AS SELECT * FROM {sql_source}")
            self.current_schema.table_identifier = self.current_view_name

            # Estimate or calculate row count
            if self.current_schema.row_count_estimate is None:
                try:
                    count_res = self._execute_sql(f"SELECT COUNT(*) FROM {self.current_view_name}").fetchone()
                    if count_res:
                        self.current_schema.row_count_estimate = count_res[0]
                except Exception:
                    pass
        else:
            self.conn.execute(f"DROP VIEW IF EXISTS {self.current_view_name}")

        return self.current_schema

    def index_xml_dataset(
        self,
        progress_callback: Callable[[float, int, int], None] | None = None,
        clean_cache: bool = False,
    ) -> None:
        """Convert current XML dataset to cached Parquet files and register view."""
        if not self.current_schema or self.current_schema.source_format != "xml":
            raise ValueError("Current dataset is not an XML dataset.")

        dataset_path = self.current_dataset_path or self.current_schema.source_path
        analysis = DatasetDetector.analyze_path(dataset_path)
        files = analysis["files"]

        cache_dir = self.xml_adapter.get_cache_path(files)
        if clean_cache and cache_dir.exists():
            import shutil
            shutil.rmtree(cache_dir, ignore_errors=True)

        cache_dir = self.xml_adapter.convert_to_parquet_streaming(
            files,
            output_dir=cache_dir,
            progress_callback=progress_callback,
        )

        sql_source = f"read_parquet('{cache_dir!s}/**/*.parquet', union_by_name=true)"
        self.current_sql_source = sql_source
        self.conn.execute(f"CREATE OR REPLACE VIEW {self.current_view_name} AS SELECT * FROM {sql_source}")
        self.current_schema.table_identifier = self.current_view_name

        count_res = self.conn.execute(f"SELECT COUNT(*) FROM {self.current_view_name}").fetchone()
        if count_res:
            self.current_schema.row_count_estimate = count_res[0]

        # Update current schema column metadata with full unified schema
        try:
            describe_df = self.conn.execute(f"DESCRIBE {self.current_view_name}").fetchdf()
            new_columns = []
            for _, row in describe_df.iterrows():
                col_name = str(row["column_name"])
                native_type = str(row["column_type"]).upper()
                is_interval = "INTERVAL" in native_type
                is_num = not is_interval and any(t in native_type for t in ["INT", "BIGINT", "DOUBLE", "FLOAT", "DECIMAL"])
                data_type = DataType.NUMERIC if is_num else (
                    DataType.DATE if any(d in native_type for d in ["DATE", "TIMESTAMP"]) else DataType.TEXT
                )
                new_columns.append(ColumnMeta(name=col_name, data_type=data_type, native_type=native_type))
            self.current_schema.columns = new_columns
        except Exception as e:
            logger.warning("Errore durante l'aggiornamento dei metadati dello schema: %s", e)

    def index_csv_dataset(
        self,
        progress_callback: Callable[[float], None] | None = None,
        clean_cache: bool = False,
    ) -> None:
        """Convert current CSV dataset to cached Parquet files and register high-speed view."""
        if not self.current_schema or self.current_schema.source_format != "csv":
            raise ValueError("Il dataset corrente non è un file CSV.")

        dataset_path = self.current_dataset_path or self.current_schema.source_path
        analysis = DatasetDetector.analyze_path(dataset_path)
        files = analysis["files"]

        cache_dir = self.csv_adapter.get_cache_path(files)
        if clean_cache and cache_dir.exists():
            import shutil
            shutil.rmtree(cache_dir, ignore_errors=True)
        cache_dir.mkdir(parents=True, exist_ok=True)

        if progress_callback:
            progress_callback(0.1)

        csv_source = self.csv_adapter.build_sql_source(files)
        target_parquet = cache_dir / "data.parquet"
        safe_target = str(target_parquet.resolve()).replace("'", "''")

        copy_sql = f"COPY (SELECT * FROM {csv_source}) TO '{safe_target}' (FORMAT PARQUET, COMPRESSION ZSTD)"
        try:
            self._execute_sql(copy_sql)
        except Exception as e:
            if self._is_parallel_csv_conflict_error(e):
                self.csv_adapter.parallel = False
                csv_source_seq = self.csv_adapter.build_sql_source(files, parallel=False)
                copy_sql_seq = f"COPY (SELECT * FROM {csv_source_seq}) TO '{safe_target}' (FORMAT PARQUET, COMPRESSION ZSTD)"
                self.conn.execute(copy_sql_seq)
            else:
                raise

        if progress_callback:
            progress_callback(0.9)

        sql_source = f"read_parquet('{cache_dir!s}/**/*.parquet', union_by_name=true)"
        self.current_sql_source = sql_source
        self.conn.execute(f"CREATE OR REPLACE VIEW {self.current_view_name} AS SELECT * FROM {sql_source}")
        self.current_schema.table_identifier = self.current_view_name
        self.clear_query_cache()
        self._count_cache.clear()
        self._distinct_cache.clear()

        count_res = self.conn.execute(f"SELECT COUNT(*) FROM {self.current_view_name}").fetchone()
        if count_res:
            self.current_schema.row_count_estimate = count_res[0]

        try:
            describe_df = self.conn.execute(f"DESCRIBE {self.current_view_name}").fetchdf()
            new_columns = []
            for _, row in describe_df.iterrows():
                col_name = str(row["column_name"])
                native_type = str(row["column_type"]).upper()
                is_interval = "INTERVAL" in native_type
                is_num = not is_interval and any(t in native_type for t in ["INT", "BIGINT", "DOUBLE", "FLOAT", "DECIMAL"])
                data_type = DataType.NUMERIC if is_num else (
                    DataType.DATE if any(d in native_type for d in ["DATE", "TIMESTAMP"]) else DataType.TEXT
                )
                new_columns.append(ColumnMeta(name=col_name, data_type=data_type, native_type=native_type))
            self.current_schema.columns = new_columns
        except Exception as e:
            logger.warning("Errore durante l'aggiornamento dei metadati dello schema CSV Parquet: %s", e)

        if progress_callback:
            progress_callback(1.0)

    def execute_query(self, spec: QuerySpec) -> QueryResult:
        """Execute query specification and return tabular results with transparent pagination caching."""
        self.ensure_view_exists()
        if not self.current_schema:
            raise RuntimeError("Nessun dataset caricato.")

        schema_cols = self.current_schema.columns
        table_ref = self.current_view_name
        is_agg = bool(spec.group_by_columns or spec.aggregations)

        # Pagination caching path: if query requests a paginated slice (limit is set)
        if spec.limit is not None:
            base_fp = f"{self.current_dataset_path}:{spec.get_base_query_fingerprint()}"
            if self._active_query_fingerprint == base_fp and self._active_query_cache_table:
                t0 = time.time()
                page_sql = f"SELECT * FROM {self._active_query_cache_table} LIMIT {spec.limit}"
                if spec.offset:
                    page_sql += f" OFFSET {spec.offset}"
                try:
                    cursor = self._execute_sql(page_sql)
                    elapsed = time.time() - t0
                    table = cursor.to_arrow_table()
                    return QueryResult(
                        columns=table.column_names,
                        total_matching_rows=self._active_query_total_count or 0,
                        execution_time_seconds=round(elapsed, 4),
                        is_aggregated=is_agg,
                        table=table,
                        from_cache=True,
                    )
                except Exception as e:
                    logger.warning("Errore lettura cache query temporanea (%s); rigenerazione...", e)
                    self.clear_query_cache()

            # Cache miss: materialize base query into temporary table
            base_spec = QuerySpec(
                filters=spec.filters,
                filter_logic=spec.filter_logic,
                global_search=spec.global_search,
                global_search_columns=spec.global_search_columns,
                global_search_logic=spec.global_search_logic,
                selected_columns=spec.selected_columns,
                group_by_columns=spec.group_by_columns,
                aggregations=spec.aggregations,
                order_by=spec.order_by,
                limit=None,
                offset=None,
            )
            base_sql = QueryBuilder.build_select_query(table_ref, base_spec, schema_cols)

            t0 = time.time()
            try:
                self._execute_sql(f"CREATE OR REPLACE TEMP TABLE {self._active_query_cache_table} AS {base_sql}")
                count_res = self._execute_sql(f"SELECT COUNT(*) FROM {self._active_query_cache_table}").fetchone()
                total_rows = int(count_res[0]) if count_res and count_res[0] is not None else 0

                self._active_query_fingerprint = base_fp
                self._active_query_total_count = total_rows

                # Update count cache as well
                count_cache_key = f"{self.current_dataset_path}:{spec.get_filter_fingerprint()}"
                self._count_cache[count_cache_key] = total_rows

                page_sql = f"SELECT * FROM {self._active_query_cache_table} LIMIT {spec.limit}"
                if spec.offset:
                    page_sql += f" OFFSET {spec.offset}"
                cursor = self._execute_sql(page_sql)
                elapsed = time.time() - t0

                table = cursor.to_arrow_table()
                return QueryResult(
                    columns=table.column_names,
                    total_matching_rows=total_rows,
                    execution_time_seconds=round(elapsed, 4),
                    is_aggregated=is_agg,
                    table=table,
                    from_cache=False,
                )
            except Exception as e:
                logger.warning("Materializzazione cache query temporanea non riuscita (%s); fallback a query diretta", e)
                self.clear_query_cache()

        # Fallback / non-paginated query path
        sql = QueryBuilder.build_select_query(table_ref, spec, schema_cols)
        t0 = time.time()
        cursor = self._execute_sql(sql)
        elapsed = time.time() - t0

        table = cursor.to_arrow_table()
        columns = table.column_names
        total_rows = table.num_rows if spec.limit is None else self.count_matching_rows(spec)

        return QueryResult(
            columns=columns,
            total_matching_rows=total_rows,
            execution_time_seconds=round(elapsed, 4),
            is_aggregated=is_agg,
            table=table,
            from_cache=False,
        )

    def count_matching_rows(self, spec: QuerySpec) -> int:
        """Count total matching rows efficiently with fast-path, temp table, and LRU caching."""
        self.ensure_view_exists()
        if not self.current_schema:
            return 0

        # Fast path for unfiltered datasets
        if not spec.has_filters_or_grouping and self.current_schema.row_count_estimate is not None:
            return self.current_schema.row_count_estimate

        # Fast path if base query matches currently active materialized query table
        if self._active_query_total_count is not None and self._active_query_fingerprint:
            base_fp = f"{self.current_dataset_path}:{spec.get_base_query_fingerprint()}"
            if self._active_query_fingerprint == base_fp:
                return self._active_query_total_count

        # Check LRU filter-fingerprint count cache
        cache_key = f"{self.current_dataset_path}:{spec.get_filter_fingerprint()}"
        if cache_key in self._count_cache:
            return self._count_cache[cache_key]

        sql = QueryBuilder.build_count_query(
            self.current_view_name,
            spec,
            self.current_schema.columns,
        )
        res = self._execute_sql(sql).fetchone()
        count = int(res[0]) if res and res[0] is not None else 0

        if len(self._count_cache) >= 100:
            keys_to_remove = list(self._count_cache.keys())[:50]
            for k in keys_to_remove:
                self._count_cache.pop(k, None)
        self._count_cache[cache_key] = count
        return count

    def get_distinct_values(self, column: str, limit: int = 100) -> list[Any]:
        """Fetch distinct non-null values for a column with caching and type awareness."""
        self.ensure_view_exists()
        if not self.current_schema:
            return []

        cache_key = (str(self.current_dataset_path), column, limit)
        if cache_key in self._distinct_cache:
            return self._distinct_cache[cache_key]

        col_sql = QueryBuilder.quote_ident(column)
        meta = self.current_schema.get_column(column)
        is_text = meta is None or meta.data_type == DataType.TEXT

        # Only apply TRIM/CAST to text columns to preserve zonemaps and vectorization
        if is_text:
            where_clause = f"{col_sql} IS NOT NULL AND TRIM(CAST({col_sql} AS VARCHAR)) != ''"
        else:
            where_clause = f"{col_sql} IS NOT NULL"

        query = (
            f"SELECT DISTINCT {col_sql} "
            f"FROM {self.current_view_name} "
            f"WHERE {where_clause} "
            f"ORDER BY {col_sql} ASC "
            f"LIMIT {limit}"
        )
        try:
            res = self._execute_sql(query).fetchall()
            vals = [r[0] for r in res]
            if len(self._distinct_cache) >= 100:
                keys_to_remove = list(self._distinct_cache.keys())[:50]
                for k in keys_to_remove:
                    self._distinct_cache.pop(k, None)
            self._distinct_cache[cache_key] = vals
            return vals
        except Exception:
            return []

    def get_column_stats(self, column: str) -> dict[str, Any]:
        """Compute basic column statistics."""
        self.ensure_view_exists()
        if not self.current_schema:
            return {}

        col_sql = QueryBuilder.quote_ident(column)
        meta = self.current_schema.get_column(column)
        is_num = meta.is_numeric() if meta else False

        if is_num:
            query = f"""
                SELECT
                    COUNT({col_sql}) as count_non_null,
                    COUNT(DISTINCT {col_sql}) as count_distinct,
                    MIN(TRY_CAST({col_sql} AS DOUBLE)) as min_val,
                    MAX(TRY_CAST({col_sql} AS DOUBLE)) as max_val,
                    ROUND(AVG(TRY_CAST({col_sql} AS DOUBLE)), 2) as avg_val
                FROM {self.current_view_name}
            """
        else:
            query = f"""
                SELECT
                    COUNT({col_sql}) as count_non_null,
                    COUNT(DISTINCT {col_sql}) as count_distinct,
                    NULL as min_val,
                    NULL as max_val,
                    NULL as avg_val
                FROM {self.current_view_name}
            """

        try:
            row = self._execute_sql(query).fetchone()
            if row:
                return {
                    "count_non_null": row[0],
                    "count_distinct": row[1],
                    "min_val": row[2],
                    "max_val": row[3],
                    "avg_val": row[4],
                }
        except Exception:
            pass
        return {}

    def export_query(
        self,
        spec: QuerySpec,
        output_file: str,
        export_format: str = "csv",
        progress_callback: Callable[[float], None] | None = None,
    ) -> int:
        """
        Stream export query results directly to disk without loading into memory.
        Returns the number of exported rows.
        """
        self.ensure_view_exists()
        if not self.current_schema:
            raise RuntimeError("Nessun dataset caricato.")

        # Ensure target directory exists
        out_path = Path(output_file)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        sql = QueryBuilder.build_export_query(
            self.current_view_name,
            spec,
            str(out_path),
            export_format=export_format,
            schema_columns=self.current_schema.columns,
        )

        res = self._execute_sql(sql).fetchone()
        exported_count = int(res[0]) if res and res[0] is not None else 0

        if progress_callback:
            progress_callback(1.0)

        return exported_count

    def close(self) -> None:
        """Release DuckDB connection and clean up temporary spill directory."""
        self.clear_query_cache()
        try:
            if hasattr(self, "conn") and self.conn:
                self.conn.close()
                self.conn = None  # type: ignore[assignment]
        except Exception as e:
            logger.debug("Errore chiusura connessione DuckDB: %s", e)
        try:
            import shutil
            if hasattr(self, "instance_spill_dir") and self.instance_spill_dir.exists():
                shutil.rmtree(self.instance_spill_dir, ignore_errors=True)
        except Exception as e:
            logger.debug("Errore rimozione instance_spill_dir: %s", e)

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()
