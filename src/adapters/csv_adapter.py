"""
CSV Adapter for streaming out-of-core data access using DuckDB.
Handles delimiters, multi-file globs, quotes, messy characters, and schema sniffing.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

import duckdb

from src.core.interfaces import IDatasetAdapter
from src.core.models import ColumnMeta, DatasetSchema, DataType
from src.core.paths import get_parquet_cache_dir


class CsvAdapter(IDatasetAdapter):
    """Adapter for CSV datasets."""

    def __init__(
        self,
        delimiter: str | None = None,
        parallel: bool | None = None,
        cache_dir: Path | None = None,
    ):
        self.delimiter = delimiter
        self.parallel = parallel
        self._cache_dir = cache_dir or get_parquet_cache_dir()

    def get_cache_path(self, path_or_files: Any) -> Path:
        """Derive cache directory for a CSV dataset based on hash of paths."""
        if isinstance(path_or_files, list):
            path_repr = "|".join(sorted(str(Path(p).resolve()) for p in path_or_files))
        else:
            path_repr = str(Path(path_or_files).resolve())
        path_hash = hashlib.md5(path_repr.encode("utf-8")).hexdigest()[:12]
        return self._cache_dir / f"csv_{path_hash}"

    def can_handle(self, path: str) -> bool:
        lower = path.lower()
        return lower.endswith((".csv", ".tsv", ".txt"))

    def sniff_delimiter(self, sample_file: str) -> str:
        """Sniff delimiter from first few lines of a sample CSV file."""
        if self.delimiter:
            return self.delimiter

        delimiters = [",", ";", "\t", "|"]
        scores = dict.fromkeys(delimiters, 0)

        try:
            with open(sample_file, encoding="utf-8", errors="replace") as f:
                lines = [f.readline() for _ in range(10)]
                lines = [line for line in lines if line.strip()]

            if not lines:
                return ","

            header = lines[0]
            for d in delimiters:
                header_count = header.count(d)
                if header_count > 0:
                    # Check consistency across sample lines
                    consistent = all(line.count(d) == header_count for line in lines[1:5])
                    if consistent:
                        scores[d] += header_count * 10
                    else:
                        scores[d] += header_count

            best_delim = max(scores, key=lambda d: scores[d])
            return best_delim if scores[best_delim] > 0 else ","
        except Exception:
            return ","

    def get_source_description(self, path: str) -> dict[str, Any]:
        return {"format": "csv"}

    def build_sql_source(
        self,
        path_or_files: Any,
        delim: str | None = None,
        parallel: bool | None = None,
    ) -> str:
        """Build the DuckDB read_csv SQL expression."""
        if isinstance(path_or_files, list):
            file_paths = [p.replace("'", "''") for p in path_or_files]
            if len(file_paths) == 1:
                files_expr = f"'{file_paths[0]}'"
            else:
                formatted_list = ", ".join(f"'{p}'" for p in file_paths)
                files_expr = f"[{formatted_list}]"
            sample_file = path_or_files[0] if path_or_files else ""
        else:
            escaped_path = str(path_or_files).replace("'", "''")
            files_expr = f"'{escaped_path}'"
            sample_file = path_or_files

        if delim is None:
            delim = self.sniff_delimiter(sample_file) if sample_file else ","

        use_parallel = self.parallel if parallel is None else parallel
        if use_parallel is False:
            parallel_clause = ", parallel=false"
        elif use_parallel is True:
            parallel_clause = ", parallel=true"
        else:
            parallel_clause = ""

        return (
            f"read_csv({files_expr}, "
            f"delim='{delim}', "
            f"header=true, "
            f"quote='\"', "
            f"escape='\"', "
            f"strict_mode=false, "
            f"null_padding=true{parallel_clause}, "
            f"ignore_errors=true, "
            f"auto_detect=true, "
            f"union_by_name=true)"
        )

    def inspect_schema(self, path_or_files: Any, duckdb_conn: duckdb.DuckDBPyConnection) -> DatasetSchema:
        """Inspect schema, column types, and sample data using DuckDB connection."""
        if isinstance(path_or_files, list):
            if not path_or_files:
                raise ValueError("Nessun file fornito per l'ispezione dello schema.")
            sample_file = path_or_files[0]
            file_count = len(path_or_files)
            total_size = sum(os.path.getsize(f) for f in path_or_files)
            source_path = os.path.commonpath(path_or_files) if file_count > 1 else sample_file
        else:
            sample_file = path_or_files
            file_count = 1
            total_size = os.path.getsize(sample_file)
            source_path = sample_file

        cache_path = self.get_cache_path(path_or_files)
        has_cache = cache_path.exists() and any(cache_path.glob("**/*.parquet"))

        row_count_est = None
        if has_cache:
            safe_cache = str(cache_path.resolve()).replace("'", "''")
            sql_source = f"read_parquet('{safe_cache}/**/*.parquet', union_by_name=true)"
            describe_rows = duckdb_conn.execute(f"DESCRIBE SELECT * FROM {sql_source} LIMIT 10").fetchall()
            sample_table = duckdb_conn.execute(f"SELECT * FROM {sql_source} LIMIT 1000").to_arrow_table()
            count_res = duckdb_conn.execute(f"SELECT COUNT(*) FROM {sql_source}").fetchone()
            if count_res:
                row_count_est = count_res[0]
        else:
            delim = self.sniff_delimiter(sample_file)
            sql_source = self.build_sql_source(path_or_files, delim=delim)

            # Inspect table structure and sample rows with automatic fallback if parallel scanner fails
            try:
                describe_rows = duckdb_conn.execute(f"DESCRIBE SELECT * FROM {sql_source} LIMIT 10").fetchall()
                sample_table = duckdb_conn.execute(f"SELECT * FROM {sql_source} LIMIT 1000").to_arrow_table()
            except Exception as e:
                err_msg = str(e).lower()
                if "parallel scanner does not support null_padding" in err_msg or "disable the parallel csv reader with parallel=false" in err_msg:
                    self.parallel = False
                    sql_source = self.build_sql_source(path_or_files, delim=delim, parallel=False)
                    describe_rows = duckdb_conn.execute(f"DESCRIBE SELECT * FROM {sql_source} LIMIT 10").fetchall()
                    sample_table = duckdb_conn.execute(f"SELECT * FROM {sql_source} LIMIT 1000").to_arrow_table()
                else:
                    raise

        columns: list[ColumnMeta] = []
        for row in describe_rows:
            col_name = str(row[0])
            native_type = str(row[1]).upper()

            sample_chunk = sample_table.column(col_name) if col_name in sample_table.column_names else None
            data_type = self._classify_type(native_type, sample_chunk)

            sample_vals = []
            if sample_chunk is not None:
                non_null = sample_chunk.drop_null()
                if len(non_null) > 0:
                    sample_vals = non_null.unique()[:5].to_pylist()

            col_meta = ColumnMeta(
                name=col_name,
                data_type=data_type,
                native_type=native_type,
                sample_values=sample_vals,
            )
            columns.append(col_meta)

        return DatasetSchema(
            source_path=source_path,
            source_format="csv",
            columns=columns,
            row_count_estimate=row_count_est,
            total_size_bytes=total_size,
            file_count=file_count,
            table_identifier="csv_source",
        )

    def _classify_type(self, native_type: str, sample_chunk: Any | None) -> DataType:
        is_interval = "INTERVAL" in native_type
        if not is_interval and any(t in native_type for t in ["INT", "BIGINT", "DOUBLE", "FLOAT", "DECIMAL", "HUGEINT", "TINYINT", "SMALLINT", "UBIGINT", "UINTEGER", "USMALLINT", "UTINYINT", "REAL", "NUMERIC"]):
            return DataType.NUMERIC
        elif any(t in native_type for t in ["DATE", "TIME", "TIMESTAMP"]):
            return DataType.DATE
        elif "BOOL" in native_type:
            return DataType.BOOLEAN
        elif "VARCHAR" in native_type or "TEXT" in native_type or "BLOB" in native_type:
            if sample_chunk is not None and len(sample_chunk) > 0:
                unique_vals = sample_chunk.drop_null().unique()
                unique_count = len(unique_vals)
                total_count = len(sample_chunk)
                # If low cardinality on sample (e.g. <= 30), treat as categorical
                if 1 < unique_count <= 30 and (unique_count / total_count) < 0.2:
                    return DataType.CATEGORICAL
            return DataType.TEXT
        return DataType.TEXT
