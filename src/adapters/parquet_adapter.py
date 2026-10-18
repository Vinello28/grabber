"""
Parquet Adapter for streaming columnar querying with DuckDB.
Supports single files, lists of files, and partitioned directories.
"""

from __future__ import annotations

import os
from typing import Any

import duckdb

from src.core.interfaces import IDatasetAdapter
from src.core.models import ColumnMeta, DatasetSchema, DataType


class ParquetAdapter(IDatasetAdapter):
    """Adapter for Parquet datasets."""

    def can_handle(self, path: str) -> bool:
        lower = path.lower()
        return lower.endswith((".parquet", ".pq"))

    def get_source_description(self, path: str) -> dict[str, Any]:
        return {"format": "parquet"}

    def build_sql_source(self, path_or_files: Any) -> str:
        if isinstance(path_or_files, list):
            file_paths = [p.replace("'", "''") for p in path_or_files]
            if len(file_paths) == 1:
                files_expr = f"'{file_paths[0]}'"
            else:
                formatted_list = ", ".join(f"'{p}'" for p in file_paths)
                files_expr = f"[{formatted_list}]"
        else:
            escaped_path = str(path_or_files).replace("'", "''")
            files_expr = f"'{escaped_path}'"

        return f"read_parquet({files_expr}, union_by_name=true)"

    def inspect_schema(self, path_or_files: Any, duckdb_conn: duckdb.DuckDBPyConnection) -> DatasetSchema:
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

        sql_source = self.build_sql_source(path_or_files)

        describe_rows = duckdb_conn.execute(f"DESCRIBE SELECT * FROM {sql_source} LIMIT 10").fetchall()
        sample_table = duckdb_conn.execute(f"SELECT * FROM {sql_source} LIMIT 1000").to_arrow_table()

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
            source_format="parquet",
            columns=columns,
            total_size_bytes=total_size,
            file_count=file_count,
            table_identifier="parquet_source",
        )

    def _classify_type(self, native_type: str, sample_chunk: Any | None) -> DataType:
        is_interval = "INTERVAL" in native_type
        if not is_interval and any(t in native_type for t in ["INT", "BIGINT", "DOUBLE", "FLOAT", "DECIMAL", "HUGEINT", "TINYINT", "SMALLINT", "UBIGINT", "UINTEGER", "USMALLINT", "UTINYINT", "REAL", "NUMERIC"]):
            return DataType.NUMERIC
        elif any(t in native_type for t in ["DATE", "TIME", "TIMESTAMP"]):
            return DataType.DATE
        elif "BOOL" in native_type:
            return DataType.BOOLEAN
        elif "VARCHAR" in native_type or "TEXT" in native_type:
            if sample_chunk is not None and len(sample_chunk) > 0:
                unique_vals = sample_chunk.drop_null().unique()
                unique_count = len(unique_vals)
                total_count = len(sample_chunk)
                if 1 < unique_count <= 30 and (unique_count / total_count) < 0.2:
                    return DataType.CATEGORICAL
            return DataType.TEXT
        return DataType.TEXT
