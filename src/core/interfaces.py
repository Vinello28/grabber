"""
Abstract interfaces for dataset adapters, query engines, and exporters.
Part of the Clean Architecture boundary.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional
from src.core.models import DatasetSchema, QueryResult, QuerySpec


class IDatasetAdapter(ABC):
    """Interface for inspecting and preparing diverse dataset formats."""

    @abstractmethod
    def can_handle(self, path: str) -> bool:
        """Return True if this adapter can process the given path or pattern."""
        pass

    @abstractmethod
    def get_source_description(self, path: str) -> Dict[str, Any]:
        """Return metadata such as total files, total bytes, format."""
        pass

    @abstractmethod
    def build_sql_source(self, path: str) -> str:
        """
        Return the SQL expression or table reference for DuckDB to query
        directly via streaming without loading everything into memory.
        """
        pass

    @abstractmethod
    def inspect_schema(self, path: str, duckdb_conn: Any) -> DatasetSchema:
        """Inspect schema, column types, and sample data using the connection."""
        pass


class IQueryEngine(ABC):
    """Interface for analytical query execution with out-of-core memory management."""

    @abstractmethod
    def connect_dataset(self, path: str) -> DatasetSchema:
        """Connect to a dataset, discover its schema, and register streaming views."""
        pass

    @abstractmethod
    def execute_query(self, spec: QuerySpec) -> QueryResult:
        """Execute a structured query specification."""
        pass

    @abstractmethod
    def count_matching_rows(self, spec: QuerySpec) -> int:
        """Return the count of rows matching the filters."""
        pass

    @abstractmethod
    def get_distinct_values(self, column: str, limit: int = 100) -> List[Any]:
        """Fetch distinct values for a categorical column."""
        pass

    @abstractmethod
    def get_column_stats(self, column: str) -> Dict[str, Any]:
        """Fetch statistics (min, max, null count, approximate unique count)."""
        pass

    @abstractmethod
    def export_query(
        self,
        spec: QuerySpec,
        output_file: str,
        export_format: str = "csv",
        progress_callback: Optional[Callable[[float], None]] = None,
    ) -> int:
        """Export filtered rows in streaming fashion to disk. Returns row count."""
        pass
