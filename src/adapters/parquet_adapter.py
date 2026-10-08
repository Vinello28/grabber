"""
Parquet Adapter for ultra-fast streaming columnar querying with DuckDB.
Supports single files, lists of files, and partitioned directories.
"""

from __future__ import annotations
import os
from typing import Any, Dict, List, Optional
import duckdb
from src.core.interfaces import IDatasetAdapter
from src.core.models import ColumnMeta, DataType, DatasetSchema


class ParquetAdapter(IDatasetAdapter):
    """Adapter for Parquet datasets."""

    def can_handle(self, path: str) -> bool:
        lower = path.lower()
        return lower.endswith(".parquet") or lower.endswith(".pq")

    def get_source_description(self, path: str) -> Dict[str, Any]:
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
            files_expr = f"'{path_or_files.replace('\'', '\'\'')}'"

        return f"read_parquet({files_expr}, union_by_name=true)"

    def inspect_schema(self, path_or_files: Any, duckdb_conn: duckdb.DuckDBPyConnection) -> DatasetSchema:
        if isinstance(path_or_files, list):
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

        describe_df = duckdb_conn.execute(f"DESCRIBE SELECT * FROM {sql_source} LIMIT 10").fetchdf()
        sample_df = duckdb_conn.execute(f"SELECT * FROM {sql_source} LIMIT 1000").fetchdf()

        columns: List[ColumnMeta] = []
        for _, row in describe_df.iterrows():
            col_name = str(row["column_name"])
            native_type = str(row["column_type"]).upper()

            data_type = self._classify_type(native_type, sample_df.get(col_name))

            sample_vals = []
            if col_name in sample_df:
                sample_vals = [
                    v for v in sample_df[col_name].dropna().unique()[:5].tolist()
                ]

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

    def _classify_type(self, native_type: str, sample_series: Optional[Any]) -> DataType:
        if any(t in native_type for t in ["INT", "BIGINT", "DOUBLE", "FLOAT", "DECIMAL", "HUGEINT", "TINYINT", "SMALLINT"]):
            return DataType.NUMERIC
        elif any(t in native_type for t in ["DATE", "TIME", "TIMESTAMP"]):
            return DataType.DATE
        elif "BOOL" in native_type:
            return DataType.BOOLEAN
        elif "VARCHAR" in native_type or "TEXT" in native_type:
            if sample_series is not None and len(sample_series) > 0:
                unique_count = sample_series.nunique()
                if 1 < unique_count <= 30 and (unique_count / len(sample_series)) < 0.2:
                    return DataType.CATEGORICAL
            return DataType.TEXT
        return DataType.TEXT
