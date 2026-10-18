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


class BooleanOperator(str, Enum):
    AND = "AND"
    OR = "OR"


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

    def has_native_numeric_type(self) -> bool:
        """Return True if column has a native numeric storage type in DuckDB."""
        if not self.is_numeric():
            return False
        nt = (self.native_type or "").upper()
        if "INTERVAL" in nt:
            return False
        numeric_keywords = (
            "INT",
            "BIGINT",
            "SMALLINT",
            "TINYINT",
            "HUGEINT",
            "UBIGINT",
            "UINTEGER",
            "USMALLINT",
            "UTINYINT",
            "DOUBLE",
            "FLOAT",
            "REAL",
            "DECIMAL",
            "NUMERIC",
        )
        return any(kw in nt for kw in numeric_keywords)

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
    term_logic: BooleanOperator = BooleanOperator.AND


@dataclass
class FilterGroup:
    id: str = ""
    rules: list[FilterRule] = field(default_factory=list)
    logic: BooleanOperator = BooleanOperator.AND  # Logic combining rules inside this group


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
    filter_logic: BooleanOperator = BooleanOperator.AND
    filter_groups: list[FilterGroup] | None = None
    filter_group_logic: BooleanOperator = BooleanOperator.AND
    global_search: str | None = None
    global_search_columns: list[str] | None = None
    global_search_logic: BooleanOperator = BooleanOperator.AND
    selected_columns: list[str] | None = None
    group_by_columns: list[str] | None = None
    aggregations: list[AggregationRule] | None = None
    order_by: list[tuple[str, bool]] | None = None  # (col, ascending)
    limit: int | None = None
    offset: int | None = None

    @property
    def has_filters_or_grouping(self) -> bool:
        """Return True if this query specifies any WHERE filters or GROUP BY/aggregations."""
        has_group_rules = bool(self.filter_groups and any(bool(g.rules) for g in (self.filter_groups or [])))
        has_any_rules = bool(self.filters) or has_group_rules
        return bool(
            has_any_rules
            or (self.global_search and self.global_search.strip())
            or self.group_by_columns
            or self.aggregations
        )

    def get_filter_fingerprint(self) -> str:
        """Deterministic fingerprint representing filter and aggregation constraints.

        Excludes offset, limit, order_by, and selected_columns since they do not affect total row count.
        """
        f_repr = tuple(
            (
                f.column,
                getattr(f.operator, "value", str(f.operator)),
                str(f.value),
                str(f.value_to),
                f.case_sensitive,
                getattr(f.term_logic, "value", str(f.term_logic)),
            )
            for f in self.filters
        )
        if self.filter_groups:
            grp_data = tuple(
                (
                    g.id,
                    getattr(g.logic, "value", str(g.logic)),
                    tuple(
                        (
                            f.column,
                            getattr(f.operator, "value", str(f.operator)),
                            str(f.value),
                            str(f.value_to),
                            f.case_sensitive,
                            getattr(f.term_logic, "value", str(f.term_logic)),
                        )
                        for f in g.rules
                    ),
                )
                for g in self.filter_groups
            )
            fg_logic = getattr(self.filter_group_logic, "value", str(self.filter_group_logic))
            groups_repr = f"{grp_data}|{fg_logic}"
        else:
            groups_repr = "none"

        grp_repr = tuple(self.group_by_columns or [])
        agg_repr = tuple(
            (a.column, getattr(a.func, "value", str(a.func)), a.alias)
            for a in (self.aggregations or [])
        )
        gs_cols = tuple(self.global_search_columns or [])
        f_logic = getattr(self.filter_logic, "value", str(self.filter_logic))
        gs_logic = getattr(self.global_search_logic, "value", str(self.global_search_logic))
        return f"{f_repr}|{f_logic}|{groups_repr}|{self.global_search}|{gs_logic}|{gs_cols}|{grp_repr}|{agg_repr}"

    def get_base_query_fingerprint(self) -> str:
        """Deterministic fingerprint representing the base query result set.

        Includes filters, aggregations, groupings, order_by, and selected_columns,
        strictly excluding limit and offset for pagination cache reuse.
        """
        filter_fp = self.get_filter_fingerprint()
        order_repr = tuple(self.order_by or [])
        cols_repr = tuple(self.selected_columns or [])
        return f"{filter_fp}|ord:{order_repr}|cols:{cols_repr}"


@dataclass
class QueryResult:
    columns: list[str]
    total_matching_rows: int
    execution_time_seconds: float
    is_aggregated: bool = False
    table: Any = None
    _df: Any = None
    _rows: list[list[Any]] | None = None
    from_cache: bool = False

    def __init__(
        self,
        columns: list[str],
        rows: list[list[Any]] | None = None,
        total_matching_rows: int = 0,
        execution_time_seconds: float = 0.0,
        is_aggregated: bool = False,
        df: Any = None,
        table: Any = None,
        from_cache: bool = False,
    ) -> None:
        self.columns = columns
        self.total_matching_rows = total_matching_rows
        self.execution_time_seconds = execution_time_seconds
        self.is_aggregated = is_aggregated
        self.table = table
        self._df = df
        self._rows = rows
        self.from_cache = from_cache

    @property
    def df(self) -> Any:
        """Lazy accessor for pandas DataFrame; converts from Arrow table on-demand."""
        if self._df is None and self.table is not None:
            self._df = self.table.to_pandas()
        return self._df

    @df.setter
    def df(self, val: Any) -> None:
        self._df = val

    @property
    def row_count(self) -> int:
        """Return number of fetched rows without eager materialization of python lists or pandas df."""
        if self.table is not None:
            return int(self.table.num_rows)
        if self._df is not None:
            return len(self._df)
        if self._rows is not None:
            return len(self._rows)
        return 0

    @property
    def rows(self) -> list[list[Any]]:
        """Lazy accessor for row lists to maintain full backward compatibility."""
        if self._rows is None:
            if self.df is not None:
                self._rows = self.df.values.tolist()
            else:
                self._rows = []
        return self._rows

    @rows.setter
    def rows(self, val: list[list[Any]]) -> None:
        self._rows = val

