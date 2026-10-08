"""
Abstract interfaces for dataset adapters, query engines, and exporters.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

from src.core.models import DatasetSchema, QueryResult, QuerySpec


class IDatasetAdapter(ABC):
    """Interface for inspecting and preparing diverse dataset formats."""

    @abstractmethod
    def can_handle(self, path: str) -> bool:
        """Return True if this adapter can process the given path or pattern."""

    @abstractmethod
    def get_source_description(self, path: str) -> dict[str, Any]:
        """Return metadata such as total files, total bytes, format."""

    @abstractmethod
    def build_sql_source(self, path_or_files: str | list[str]) -> str:
        """
        Return the SQL expression or table reference for DuckDB to query
        directly via streaming without loading everything into memory.
        """

    @abstractmethod
    def inspect_schema(self, path_or_files: str | list[str], duckdb_conn: Any) -> DatasetSchema:
        """Inspect schema, column types, and sample data using the connection."""


class IQueryEngine(ABC):
    """Interface for analytical query execution with out-of-core memory management."""

    @abstractmethod
    def connect_dataset(self, path: str) -> DatasetSchema:
        """Connect to a dataset, discover its schema, and register streaming views."""

    @abstractmethod
    def execute_query(self, spec: QuerySpec) -> QueryResult:
        """Execute a structured query specification."""

    @abstractmethod
    def count_matching_rows(self, spec: QuerySpec) -> int:
        """Return the count of rows matching the filters."""

    @abstractmethod
    def get_distinct_values(self, column: str, limit: int = 100) -> list[Any]:
        """Fetch distinct values for a categorical column."""

    @abstractmethod
    def get_column_stats(self, column: str) -> dict[str, Any]:
        """Fetch statistics (min, max, null count, approximate unique count)."""

    @abstractmethod
    def export_query(
        self,
        spec: QuerySpec,
        output_file: str,
        export_format: str = "csv",
        progress_callback: Callable[[float], None] | None = None,
    ) -> int:
        """Export filtered rows in streaming fashion to disk. Returns row count."""

    @abstractmethod
    def close(self) -> None:
        """Release database connections and clean temporary resources."""

