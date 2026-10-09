"""
SQL Query Builder for DuckDB.
Safely translates domain QuerySpec models into high-performance,
vectorized SQL expressions with type safety and escaping.
"""

from __future__ import annotations

import math
import re

from src.core.models import (
    AggregationFunc,
    BooleanOperator,
    ColumnMeta,
    DataType,
    FilterOperator,
    FilterRule,
    QuerySpec,
)


class QueryBuilder:
    """Compiles domain QuerySpec objects into DuckDB SQL."""

    @staticmethod
    def quote_ident(ident: str) -> str:
        """Escape and quote an SQL column identifier."""
        clean = str(ident).replace('"', '""')
        return f'"{clean}"'

    @staticmethod
    def escape_str_literal(val: str) -> str:
        """Escape a string literal for SQL."""
        return str(val).replace("'", "''")

    @staticmethod
    def parse_search_tokens(text: str) -> list[str]:
        """
        Extract search tokens from raw input text.
        If the text contains commas, splits by comma (allowing multi-word phrases as single tokens).
        Otherwise, splits by whitespace.
        Strips straight quotes ("" and '') and smart/curly quotes (“”‘’«»`) and whitespace from each token.
        """
        if not text:
            return []
        raw = str(text).strip()
        if not raw:
            return []

        quote_chars = '"\'“”‘’«»`'
        stripped_raw = raw.strip(quote_chars).strip()
        if not stripped_raw:
            return []

        parts = stripped_raw.split(",") if "," in stripped_raw else stripped_raw.split()
        tokens: list[str] = []
        for p in parts:
            token = p.strip().strip(quote_chars).strip()
            if token:
                tokens.append(token)
        return tokens

    @classmethod
    def build_where_clause(
        cls,
        spec: QuerySpec,
        schema_columns: list[ColumnMeta] | None = None,
    ) -> str:
        """Compile filters and global search into a single WHERE clause."""
        global_search_pred: str | None = None

        # 1. Global Search
        if spec.global_search and spec.global_search.strip():
            tokens = cls.parse_search_tokens(spec.global_search)
            if tokens:
                search_cols = spec.global_search_columns
                if not search_cols and schema_columns:
                    # Default to all text/categorical columns
                    search_cols = [
                        c.name for c in schema_columns
                        if c.data_type in (DataType.TEXT, DataType.CATEGORICAL, DataType.UNKNOWN)
                    ]

                if search_cols:
                    term_logic_op = (
                        spec.global_search_logic.value
                        if isinstance(spec.global_search_logic, BooleanOperator)
                        else str(spec.global_search_logic)
                    )
                    join_op = f" {term_logic_op} "
                    if len(tokens) > 1:
                        col_predicates = []
                        for c in search_cols:
                            c_sql = cls.quote_ident(c)
                            c_words = [
                                f"LOWER(CAST({c_sql} AS VARCHAR)) LIKE '%{cls.escape_str_literal(t.lower())}%'"
                                for t in tokens
                            ]
                            col_predicates.append(f"({join_op.join(c_words)})")
                        global_search_pred = f"({' OR '.join(col_predicates)})"
                    else:
                        term = cls.escape_str_literal(tokens[0].lower())
                        col_predicates = [
                            f"LOWER(CAST({cls.quote_ident(c)} AS VARCHAR)) LIKE '%{term}%'"
                            for c in search_cols
                        ]
                        global_search_pred = f"({' OR '.join(col_predicates)})"

        # 2. Dynamic Column Filters
        col_type_map = {c.name: c for c in schema_columns} if schema_columns else {}
        filter_preds: list[str] = []

        for f in spec.filters:
            col_sql = cls.quote_ident(f.column)
            meta = col_type_map.get(f.column)
            is_num = meta.is_numeric() if meta else False

            pred = cls._build_filter_predicate(f, col_sql, is_numeric=is_num)
            if pred:
                filter_preds.append(pred)

        filter_logic_op = (
            spec.filter_logic.value
            if isinstance(spec.filter_logic, BooleanOperator)
            else str(spec.filter_logic)
        )

        filters_combined: str | None = None
        if filter_preds:
            if len(filter_preds) == 1:
                filters_combined = filter_preds[0]
            else:
                if filter_logic_op == "OR":
                    filters_combined = f"({' OR '.join(filter_preds)})"
                else:
                    filters_combined = " AND ".join(filter_preds)

        if global_search_pred and filters_combined:
            return f"WHERE {global_search_pred} AND {filters_combined}"
        elif global_search_pred:
            return f"WHERE {global_search_pred}"
        elif filters_combined:
            return f"WHERE {filters_combined}"
        else:
            return ""

    @classmethod
    def _build_filter_predicate(
        cls,
        f: FilterRule,
        col_sql: str,
        is_numeric: bool = False,
    ) -> str | None:
        """Translate a single FilterRule into an SQL condition."""
        op = f.operator
        val = f.value

        # Nullability checks
        if op == FilterOperator.IS_NULL:
            return f"({col_sql} IS NULL OR TRIM(CAST({col_sql} AS VARCHAR)) = '')"
        if op == FilterOperator.IS_NOT_NULL:
            return f"({col_sql} IS NOT NULL AND TRIM(CAST({col_sql} AS VARCHAR)) != '')"

        if val is None or (isinstance(val, str) and not val.strip()):
            return None

        # Strip outer quotes and whitespace
        clean_val = str(val).strip().strip('"\'“”‘’«»`').strip()
        if not clean_val:
            return None

        # Text matching
        if op == FilterOperator.CONTAINS:
            base = f"CAST({col_sql} AS VARCHAR)" if f.case_sensitive else f"LOWER(CAST({col_sql} AS VARCHAR))"
            tokens = cls.parse_search_tokens(clean_val)
            if not tokens:
                return None
            term_op = (
                f.term_logic.value
                if isinstance(f.term_logic, BooleanOperator)
                else str(f.term_logic)
            )
            join_op = f" {term_op} "
            if len(tokens) > 1 and not f.case_sensitive:
                word_preds = [f"{base} LIKE '%{cls.escape_str_literal(t.lower())}%'" for t in tokens]
                return f"({join_op.join(word_preds)})"
            elif len(tokens) > 1 and f.case_sensitive:
                word_preds = [f"{base} LIKE '%{cls.escape_str_literal(t)}%'" for t in tokens]
                return f"({join_op.join(word_preds)})"
            esc = cls.escape_str_literal(tokens[0] if f.case_sensitive else tokens[0].lower())
            return f"{base} LIKE '%{esc}%'"

        if op == FilterOperator.NOT_CONTAINS:
            base = f"CAST({col_sql} AS VARCHAR)" if f.case_sensitive else f"LOWER(CAST({col_sql} AS VARCHAR))"
            tokens = cls.parse_search_tokens(clean_val)
            if not tokens:
                return None
            term_op = (
                f.term_logic.value
                if isinstance(f.term_logic, BooleanOperator)
                else str(f.term_logic)
            )
            join_op = f" {term_op} "
            if len(tokens) > 1:
                preds = [
                    f"{base} NOT LIKE '%{cls.escape_str_literal(t if f.case_sensitive else t.lower())}%'"
                    for t in tokens
                ]
                return f"({col_sql} IS NULL OR ({join_op.join(preds)}))"
            esc = cls.escape_str_literal(tokens[0] if f.case_sensitive else tokens[0].lower())
            return f"({col_sql} IS NULL OR {base} NOT LIKE '%{esc}%')"

        if op == FilterOperator.STARTS_WITH:
            esc = cls.escape_str_literal(clean_val.lower() if not f.case_sensitive else clean_val)
            base = f"CAST({col_sql} AS VARCHAR)" if f.case_sensitive else f"LOWER(CAST({col_sql} AS VARCHAR))"
            return f"{base} LIKE '{esc}%'"

        if op == FilterOperator.ENDS_WITH:
            esc = cls.escape_str_literal(clean_val.lower() if not f.case_sensitive else clean_val)
            base = f"CAST({col_sql} AS VARCHAR)" if f.case_sensitive else f"LOWER(CAST({col_sql} AS VARCHAR))"
            return f"{base} LIKE '%{esc}'"

        if op == FilterOperator.EQUALS:
            if is_numeric:
                try:
                    num_val = float(str(val).replace(",", "."))
                    if math.isfinite(num_val):
                        return f"TRY_CAST({col_sql} AS DOUBLE) = {num_val}"
                except ValueError:
                    pass
            esc = cls.escape_str_literal(clean_val.lower() if not f.case_sensitive else clean_val)
            base = f"CAST({col_sql} AS VARCHAR)" if f.case_sensitive else f"LOWER(CAST({col_sql} AS VARCHAR))"
            return f"{base} = '{esc}'"

        if op == FilterOperator.NOT_EQUALS:
            if is_numeric:
                try:
                    num_val = float(str(val).replace(",", "."))
                    if math.isfinite(num_val):
                        return f"TRY_CAST({col_sql} AS DOUBLE) IS DISTINCT FROM {num_val}"
                except ValueError:
                    pass
            esc = cls.escape_str_literal(clean_val.lower() if not f.case_sensitive else clean_val)
            base = f"CAST({col_sql} AS VARCHAR)" if f.case_sensitive else f"LOWER(CAST({col_sql} AS VARCHAR))"
            return f"({col_sql} IS NULL OR {base} != '{esc}')"

        if op == FilterOperator.REGEX:
            raw_regex = str(val).strip()
            try:
                re.compile(raw_regex)
            except re.error:
                return None
            esc = cls.escape_str_literal(raw_regex)
            flags = "" if f.case_sensitive else "(?i)"
            return f"regexp_matches(CAST({col_sql} AS VARCHAR), '{flags}{esc}')"

        # Numeric comparisons
        if op in (FilterOperator.GT, FilterOperator.GTE, FilterOperator.LT, FilterOperator.LTE):
            try:
                num_val = float(str(val).replace(",", "."))
                if not math.isfinite(num_val):
                    return None
                return f"TRY_CAST({col_sql} AS DOUBLE) {op.value} {num_val}"
            except ValueError:
                return None

        if op == FilterOperator.BETWEEN:
            try:
                if f.value_to is not None:
                    raw_min, raw_max = val, f.value_to
                elif isinstance(val, (tuple, list)) and len(val) == 2:
                    raw_min, raw_max = val[0], val[1]
                else:
                    return None
                min_v = float(str(raw_min).replace(",", "."))
                max_v = float(str(raw_max).replace(",", "."))
                if not (math.isfinite(min_v) and math.isfinite(max_v)):
                    return None
                if min_v > max_v:
                    min_v, max_v = max_v, min_v
                return f"TRY_CAST({col_sql} AS DOUBLE) BETWEEN {min_v} AND {max_v}"
            except (ValueError, TypeError):
                return None

        # Categorical lists
        if op in (FilterOperator.IN_LIST, FilterOperator.NOT_IN_LIST) and isinstance(val, (list, tuple, set)) and len(val) > 0:
            esc_items = [f"'{cls.escape_str_literal(str(item))}'" for item in val]
            items_str = ", ".join(esc_items)
            if op == FilterOperator.IN_LIST:
                return f"CAST({col_sql} AS VARCHAR) IN ({items_str})"
            else:
                return f"({col_sql} IS NULL OR CAST({col_sql} AS VARCHAR) NOT IN ({items_str}))"

        return None

    @classmethod
    def build_select_query(
        cls,
        table_ref: str,
        spec: QuerySpec,
        schema_columns: list[ColumnMeta] | None = None,
    ) -> str:
        """Compile a full SELECT query with filtering, grouping, sorting, and pagination."""
        where_clause = cls.build_where_clause(spec, schema_columns)

        # Check if query is an aggregation / group by
        if spec.group_by_columns or spec.aggregations:
            return cls._build_aggregated_query(table_ref, spec, where_clause)

        # Standard projection query
        select_cols = (
            ", ".join(cls.quote_ident(c) for c in spec.selected_columns)
            if spec.selected_columns
            else "*"
        )

        query = f"SELECT {select_cols} FROM {table_ref} {where_clause}".strip()

        # Ordering
        if spec.order_by:
            order_items = []
            for col, asc in spec.order_by:
                direction = "ASC" if asc else "DESC"
                order_items.append(f"{cls.quote_ident(col)} {direction}")
            query += " ORDER BY " + ", ".join(order_items)

        # Pagination
        if spec.limit is not None:
            query += f" LIMIT {int(spec.limit)}"
        if spec.offset is not None:
            query += f" OFFSET {int(spec.offset)}"

        return query

    @classmethod
    def _build_aggregated_query(
        cls,
        table_ref: str,
        spec: QuerySpec,
        where_clause: str,
    ) -> str:
        """Build GROUP BY with aggregations."""
        select_parts: list[str] = []
        group_by_parts: list[str] = []

        if spec.group_by_columns:
            for col in spec.group_by_columns:
                quoted = cls.quote_ident(col)
                select_parts.append(quoted)
                group_by_parts.append(quoted)

        if spec.aggregations:
            for agg in spec.aggregations:
                alias_quoted = cls.quote_ident(agg.display_alias)
                expr = cls._build_agg_expr(agg.func, agg.column)
                select_parts.append(f"{expr} AS {alias_quoted}")

        if not select_parts:
            select_parts.append("COUNT(*) AS total_count")

        select_clause = ", ".join(select_parts)
        query = f"SELECT {select_clause} FROM {table_ref} {where_clause}".strip()

        if group_by_parts:
            query += " GROUP BY " + ", ".join(group_by_parts)

        if spec.order_by:
            order_items = []
            for col, asc in spec.order_by:
                direction = "ASC" if asc else "DESC"
                order_items.append(f"{cls.quote_ident(col)} {direction}")
            query += " ORDER BY " + ", ".join(order_items)
        elif spec.aggregations:
            # Default order by first aggregation DESC
            first_agg_alias = cls.quote_ident(spec.aggregations[0].display_alias)
            query += f" ORDER BY {first_agg_alias} DESC"

        if spec.limit is not None:
            query += f" LIMIT {int(spec.limit)}"
        if spec.offset is not None:
            query += f" OFFSET {int(spec.offset)}"

        return query

    @classmethod
    def _build_agg_expr(cls, func: AggregationFunc, col: str) -> str:
        if col == "*" or (func == AggregationFunc.COUNT and col == "*"):
            return "COUNT(*)"
        col_quoted = cls.quote_ident(col)
        if func == AggregationFunc.COUNT:
            return f"COUNT({col_quoted})"
        if func == AggregationFunc.COUNT_DISTINCT:
            return f"COUNT(DISTINCT {col_quoted})"
        if func == AggregationFunc.SUM:
            return f"SUM(TRY_CAST({col_quoted} AS DOUBLE))"
        if func == AggregationFunc.AVG:
            return f"ROUND(AVG(TRY_CAST({col_quoted} AS DOUBLE)), 2)"
        if func == AggregationFunc.MIN:
            return f"MIN({col_quoted})"
        if func == AggregationFunc.MAX:
            return f"MAX({col_quoted})"
        return f"COUNT({col_quoted})"

    @classmethod
    def build_count_query(
        cls,
        table_ref: str,
        spec: QuerySpec,
        schema_columns: list[ColumnMeta] | None = None,
    ) -> str:
        """Build query to count matching rows without fetching them."""
        where_clause = cls.build_where_clause(spec, schema_columns)
        if spec.group_by_columns or spec.aggregations:
            count_spec = QuerySpec(
                filters=spec.filters,
                global_search=spec.global_search,
                global_search_columns=spec.global_search_columns,
                group_by_columns=spec.group_by_columns,
                aggregations=spec.aggregations,
                limit=None,
                offset=None,
            )
            sub = cls._build_aggregated_query(table_ref, count_spec, where_clause)
            return f"SELECT COUNT(*) FROM ({sub}) AS subquery"
        return f"SELECT COUNT(*) FROM {table_ref} {where_clause}".strip()

    @classmethod
    def build_export_query(
        cls,
        table_ref: str,
        spec: QuerySpec,
        output_path: str,
        export_format: str = "csv",
        schema_columns: list[ColumnMeta] | None = None,
    ) -> str:
        """
        Build an out-of-core COPY query for direct streaming export to disk.
        Does not load the result into Python memory.
        """
        # Exclude limit/offset from export query unless explicitly intended
        export_spec = QuerySpec(
            filters=spec.filters,
            global_search=spec.global_search,
            global_search_columns=spec.global_search_columns,
            selected_columns=spec.selected_columns,
            group_by_columns=spec.group_by_columns,
            aggregations=spec.aggregations,
            order_by=spec.order_by,
        )

        inner_select = cls.build_select_query(table_ref, export_spec, schema_columns)
        clean_out = cls.escape_str_literal(output_path)

        if export_format.lower() == "parquet":
            return f"COPY ({inner_select}) TO '{clean_out}' (FORMAT PARQUET, COMPRESSION ZSTD)"
        elif export_format.lower() == "json":
            return f"COPY ({inner_select}) TO '{clean_out}' (FORMAT JSON, ARRAY true)"
        else:  # CSV default
            return f"COPY ({inner_select}) TO '{clean_out}' WITH (HEADER true, DELIMITER ',')"
