"""
Core domain models for the Big Data Analytical Query Application.
Designed according to Clean Architecture principles.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


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
    sample_values: List[Any] = field(default_factory=list)
    unique_count_estimate: Optional[int] = None
    min_val: Optional[Any] = None
    max_val: Optional[Any] = None

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
    columns: List[ColumnMeta]
    row_count_estimate: Optional[int] = None
    total_size_bytes: Optional[int] = None
    table_identifier: str = "dataset"
    file_count: int = 1

    @property
    def column_names(self) -> List[str]:
        return [col.name for col in self.columns]

    def get_column(self, name: str) -> Optional[ColumnMeta]:
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
    alias: Optional[str] = None

    @property
    def display_alias(self) -> str:
        if self.alias:
            return self.alias
        return f"{self.func.value}_{self.column}"


@dataclass
class QuerySpec:
    filters: List[FilterRule] = field(default_factory=list)
    global_search: Optional[str] = None
    global_search_columns: Optional[List[str]] = None
    selected_columns: Optional[List[str]] = None
    group_by_columns: Optional[List[str]] = None
    aggregations: Optional[List[AggregationRule]] = None
    order_by: Optional[List[Tuple[str, bool]]] = None  # (col, ascending)
    limit: Optional[int] = None
    offset: Optional[int] = None


@dataclass
class QueryResult:
    columns: List[str]
    rows: List[List[Any]]
    total_matching_rows: int
    execution_time_seconds: float
    is_aggregated: bool = False
