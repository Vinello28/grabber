"""
DuckDB Analytical Query Engine.
Handles out-of-core streaming SQL, memory boundaries, disk spillover,
and dynamic view registration.
"""

from __future__ import annotations
import os
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
import duckdb

from src.core.interfaces import IQueryEngine
from src.core.models import (
    ColumnMeta,
    DatasetSchema,
    QueryResult,
    QuerySpec,
)
from src.adapters.detector import DatasetDetector
from src.adapters.csv_adapter import CsvAdapter
from src.adapters.parquet_adapter import ParquetAdapter
from src.adapters.xml_adapter import XmlAdapter
from src.engine.query_builder import QueryBuilder
from src.engine.resource_monitor import ResourceMonitor


class DuckDBEngine(IQueryEngine):
    """Execution engine for big data analytics using DuckDB."""

    def __init__(
        self,
        memory_limit: Optional[str] = None,
        threads: Optional[int] = None,
        temp_dir: Optional[str] = None,
    ):
        self.temp_dir = Path(temp_dir or ".cache/duckdb_spill")
        self.temp_dir.mkdir(parents=True, exist_ok=True)

        self.memory_limit = memory_limit or ResourceMonitor.calculate_safe_memory_limit()
        self.threads = threads or (os.cpu_count() or 4)

        # Initialize DuckDB in-memory session with disk spillover configured
        self.conn = duckdb.connect(database=":memory:")
        self._configure_connection()

        self.current_schema: Optional[DatasetSchema] = None
        self.current_view_name = "current_dataset"
        self.current_dataset_path: Optional[str] = None
        self.current_sql_source: Optional[str] = None

        # Adapters
        self.csv_adapter = CsvAdapter()
        self.parquet_adapter = ParquetAdapter()
        self.xml_adapter = XmlAdapter()

    def _configure_connection(self) -> None:
        """Apply performance and memory safety pragmas."""
        self.conn.execute(f"PRAGMA max_memory='{self.memory_limit}'")
        self.conn.execute(f"PRAGMA threads={self.threads}")
        self.conn.execute(f"PRAGMA temp_directory='{str(self.temp_dir)}'")
        self.conn.execute("PRAGMA preserve_insertion_order=false")

    def has_active_view(self) -> bool:
        """Check if current_dataset table/view exists in DuckDB catalog."""
        try:
            res = self.conn.execute(
                "SELECT 1 FROM information_schema.tables WHERE table_name = ?",
                [self.current_view_name],
            ).fetchone()
            return res is not None
        except Exception:
            return False

    def ensure_view_exists(self) -> None:
        """Ensure current_dataset view exists, recreating it if necessary."""
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

        if self.current_sql_source:
            self.conn.execute(
                f"CREATE OR REPLACE VIEW {self.current_view_name} AS SELECT * FROM {self.current_sql_source}"
            )
            return

        raise RuntimeError(
            "Nessun dataset attivo caricato nel motore. Seleziona e carica un dataset prima di eseguire query."
        )

    def connect_dataset(self, path: str) -> DatasetSchema:
        """
        Analyze path, select adapter, inspect schema, and register
        a streaming view without loading full data into RAM.
        """
        analysis = DatasetDetector.analyze_path(path)
        fmt = analysis["format"]
        files = analysis["files"]
        self.current_dataset_path = path

        if fmt == "csv":
            self.current_schema = self.csv_adapter.inspect_schema(files, self.conn)
            sql_source = self.csv_adapter.build_sql_source(files)
        elif fmt == "parquet":
            self.current_schema = self.parquet_adapter.inspect_schema(files, self.conn)
            sql_source = self.parquet_adapter.build_sql_source(files)
        elif fmt == "xml":
            self.current_schema = self.xml_adapter.inspect_schema(files, self.conn)
            cache_path = self.xml_adapter.get_cache_path(files)
            if cache_path.exists() and any(cache_path.glob("**/*.parquet")):
                sql_source = f"read_parquet('{str(cache_path)}/**/*.parquet', union_by_name=true)"
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
                    count_res = self.conn.execute(f"SELECT COUNT(*) FROM {self.current_view_name}").fetchone()
                    if count_res:
                        self.current_schema.row_count_estimate = count_res[0]
                except Exception:
                    pass
        else:
            self.conn.execute(f"DROP VIEW IF EXISTS {self.current_view_name}")

        return self.current_schema

    def index_xml_dataset(
        self,
        progress_callback: Optional[Callable[[float, int, int], None]] = None,
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

        sql_source = f"read_parquet('{str(cache_dir)}/**/*.parquet', union_by_name=true)"
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
                is_num = any(t in native_type for t in ["INT", "BIGINT", "DOUBLE", "FLOAT", "DECIMAL"])
                data_type = DataType.NUMERIC if is_num else (
                    DataType.DATE if any(d in native_type for d in ["DATE", "TIMESTAMP"]) else DataType.TEXT
                )
                new_columns.append(ColumnMeta(name=col_name, data_type=data_type, native_type=native_type))
            self.current_schema.columns = new_columns
        except Exception:
            pass

    def execute_query(self, spec: QuerySpec) -> QueryResult:
        """Execute query specification and return tabular results."""
        self.ensure_view_exists()
        if not self.current_schema:
            raise RuntimeError("Nessun dataset caricato.")

        schema_cols = self.current_schema.columns
        table_ref = self.current_view_name

        sql = QueryBuilder.build_select_query(table_ref, spec, schema_cols)

        t0 = time.time()
        cursor = self.conn.execute(sql)
        elapsed = time.time() - t0

        df = cursor.fetchdf()
        columns = df.columns.tolist()
        rows = df.values.tolist()

        is_agg = bool(spec.group_by_columns or spec.aggregations)
        total_rows = len(rows) if (spec.limit is None or is_agg) else self.count_matching_rows(spec)

        return QueryResult(
            columns=columns,
            rows=rows,
            total_matching_rows=total_rows,
            execution_time_seconds=round(elapsed, 3),
            is_aggregated=is_agg,
        )

    def count_matching_rows(self, spec: QuerySpec) -> int:
        """Count total matching rows efficiently without fetching all data."""
        self.ensure_view_exists()
        if not self.current_schema:
            return 0

        sql = QueryBuilder.build_count_query(
            self.current_view_name,
            spec,
            self.current_schema.columns,
        )
        res = self.conn.execute(sql).fetchone()
        return res[0] if res else 0

    def get_distinct_values(self, column: str, limit: int = 100) -> List[Any]:
        """Fetch distinct non-null values for a column."""
        self.ensure_view_exists()
        if not self.current_schema:
            return []

        col_sql = QueryBuilder.quote_ident(column)
        query = (
            f"SELECT DISTINCT {col_sql} "
            f"FROM {self.current_view_name} "
            f"WHERE {col_sql} IS NOT NULL AND TRIM(CAST({col_sql} AS VARCHAR)) != '' "
            f"ORDER BY {col_sql} ASC "
            f"LIMIT {limit}"
        )
        try:
            res = self.conn.execute(query).fetchall()
            return [r[0] for r in res]
        except Exception:
            return []

    def get_column_stats(self, column: str) -> Dict[str, Any]:
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
            row = self.conn.execute(query).fetchone()
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
        progress_callback: Optional[Callable[[float], None]] = None,
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

        count_matching = self.count_matching_rows(spec)

        sql = QueryBuilder.build_export_query(
            self.current_view_name,
            spec,
            str(out_path),
            export_format=export_format,
            schema_columns=self.current_schema.columns,
        )

        self.conn.execute(sql)
        if progress_callback:
            progress_callback(1.0)

        return count_matching
