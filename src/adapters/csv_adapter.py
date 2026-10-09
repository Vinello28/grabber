"""
CSV Adapter for streaming out-of-core data access using DuckDB.
Handles delimiters, multi-file globs, quotes, messy characters, and schema sniffing.
"""

from __future__ import annotations

import os
from typing import Any

import duckdb

from src.core.interfaces import IDatasetAdapter
from src.core.models import ColumnMeta, DatasetSchema, DataType


class CsvAdapter(IDatasetAdapter):
    """Adapter for CSV datasets."""

    def __init__(self, delimiter: str | None = None, parallel: bool | None = None):
        self.delimiter = delimiter
        self.parallel = parallel

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

        delim = self.sniff_delimiter(sample_file)
        sql_source = self.build_sql_source(path_or_files, delim=delim)

        # Inspect table structure and sample rows with automatic fallback if parallel scanner fails
        try:
            describe_df = duckdb_conn.execute(f"DESCRIBE SELECT * FROM {sql_source} LIMIT 10").fetchdf()
            sample_df = duckdb_conn.execute(f"SELECT * FROM {sql_source} LIMIT 1000").fetchdf()
        except Exception as e:
            err_msg = str(e).lower()
            if "parallel scanner does not support null_padding" in err_msg or "disable the parallel csv reader with parallel=false" in err_msg:
                self.parallel = False
                sql_source = self.build_sql_source(path_or_files, delim=delim, parallel=False)
                describe_df = duckdb_conn.execute(f"DESCRIBE SELECT * FROM {sql_source} LIMIT 10").fetchdf()
                sample_df = duckdb_conn.execute(f"SELECT * FROM {sql_source} LIMIT 1000").fetchdf()
            else:
                raise

        columns: list[ColumnMeta] = []
        for _, row in describe_df.iterrows():
            col_name = str(row["column_name"])
            native_type = str(row["column_type"]).upper()

            # Determine DataType enum
            data_type = self._classify_type(native_type, sample_df.get(col_name))

            sample_vals = []
            if col_name in sample_df:
                sample_vals = list(sample_df[col_name].dropna().unique()[:5])

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
            total_size_bytes=total_size,
            file_count=file_count,
            table_identifier="csv_source",
        )

    def _classify_type(self, native_type: str, sample_series: Any | None) -> DataType:
        is_interval = "INTERVAL" in native_type
        if not is_interval and any(t in native_type for t in ["INT", "BIGINT", "DOUBLE", "FLOAT", "DECIMAL", "HUGEINT", "TINYINT", "SMALLINT"]):
            return DataType.NUMERIC
        elif any(t in native_type for t in ["DATE", "TIME", "TIMESTAMP"]):
            return DataType.DATE
        elif "BOOL" in native_type:
            return DataType.BOOLEAN
        elif "VARCHAR" in native_type or "TEXT" in native_type or "BLOB" in native_type:
            if sample_series is not None and len(sample_series) > 0:
                unique_count = sample_series.nunique()
                # If low cardinality on sample (e.g. <= 30), treat as categorical
                if 1 < unique_count <= 30 and (unique_count / len(sample_series)) < 0.2:
                    return DataType.CATEGORICAL
            return DataType.TEXT
        return DataType.TEXT
