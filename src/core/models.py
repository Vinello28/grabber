"""
Core domain models for the analytical query engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class DataType(str, Enum):
    TEXT = "text"
    NUMERIC = "numeric"
    CATEGORICAL = "categorical"
    DATE = "date"
    BOOLEAN = "boolean"
    UNKNOWN = "unknown"


class FilterOperator(str, Enum):
    # Text operators
    CONTAINS = "contains"
    NOT_CONTAINS = "not_contains"
    STARTS_WITH = "starts_with"
    ENDS_WITH = "ends_with"
    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    REGEX = "regex"

    # Numeric / Comparison operators
    GT = ">"
    GTE = ">="
    LT = "<"
    LTE = "<="
    BETWEEN = "between"

    # Categorical operators
    IN_LIST = "in"
    NOT_IN_LIST = "not_in"

    # Nullability operators
    IS_NULL = "is_null"
    IS_NOT_NULL = "is_not_null"


class AggregationFunc(str, Enum):
    COUNT = "count"
    COUNT_DISTINCT = "count_distinct"
    SUM = "sum"
    AVG = "avg"
    MIN = "min"
    MAX = "max"


@dataclass
class ColumnMeta:
    name: str
    data_type: DataType
    native_type: str = "VARCHAR"
    is_nullable: bool = True
    sample_values: list[Any] = field(default_factory=list)
    unique_count_estimate: int | None = None
    min_val: Any | None = None
    max_val: Any | None = None

    def is_numeric(self) -> bool:
        return self.data_type == DataType.NUMERIC

    def is_text(self) -> bool:
        return self.data_type in (DataType.TEXT, DataType.CATEGORICAL)

    def is_categorical(self) -> bool:
        return self.data_type == DataType.CATEGORICAL


@dataclass
class DatasetSchema:
    source_path: str
    source_format: str  # 'csv', 'parquet', 'xml', 'directory'
    columns: list[ColumnMeta]
    row_count_estimate: int | None = None
    total_size_bytes: int | None = None
    table_identifier: str = "dataset"
    file_count: int = 1

    @property
    def column_names(self) -> list[str]:
        return [col.name for col in self.columns]

    def get_column(self, name: str) -> ColumnMeta | None:
        for col in self.columns:
            if col.name == name:
                return col
        return None


@dataclass
class FilterRule:
    column: str
    operator: FilterOperator
    value: Any = None
    value_to: Any = None  # Used for BETWEEN
    case_sensitive: bool = False


@dataclass
class AggregationRule:
    column: str
    func: AggregationFunc
    alias: str | None = None

    @property
    def display_alias(self) -> str:
        if self.alias:
            return self.alias
        func_name = self.func.value if hasattr(self.func, "value") else str(self.func)
        return f"{func_name}_{self.column}"


@dataclass
class QuerySpec:
    filters: list[FilterRule] = field(default_factory=list)
    global_search: str | None = None
    global_search_columns: list[str] | None = None
    selected_columns: list[str] | None = None
    group_by_columns: list[str] | None = None
    aggregations: list[AggregationRule] | None = None
    order_by: list[tuple[str, bool]] | None = None  # (col, ascending)
    limit: int | None = None
    offset: int | None = None


@dataclass
class QueryResult:
    columns: list[str]
    rows: list[list[Any]]
    total_matching_rows: int
    execution_time_seconds: float
    is_aggregated: bool = False
