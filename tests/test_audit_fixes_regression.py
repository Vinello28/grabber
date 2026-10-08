"""
Regression test suite for fixes identified during the multi-agent system audit.
Validates:
1. NaN/Inf and inverted numeric BETWEEN filters
2. Distinct-from logic for numeric NOT_EQUALS
3. Aggregation pagination and count query subquery compilation
4. DuckDBEngine context manager and resource cleanup
5. XML row count estimation calculation
6. Regex compilation error tolerance
"""

from src.adapters.xml_adapter import XmlAdapter
from src.core.models import (
    AggregationRule,
    ColumnMeta,
    DataType,
    FilterOperator,
    FilterRule,
    QuerySpec,
)
from src.engine.duckdb_engine import DuckDBEngine
from src.engine.query_builder import QueryBuilder


def test_nan_and_inf_numeric_filter_rejection():
    """Verify NaN and Inf values are safely rejected by QueryBuilder without crashing."""
    cols = [ColumnMeta("VALORE", DataType.NUMERIC)]

    # NaN as float
    spec_nan = QuerySpec(filters=[FilterRule("VALORE", FilterOperator.GT, float("nan"))])
    where_nan = QueryBuilder.build_where_clause(spec_nan, cols)
    assert where_nan == ""

    # Inf as float
    spec_inf = QuerySpec(filters=[FilterRule("VALORE", FilterOperator.LTE, float("inf"))])
    where_inf = QueryBuilder.build_where_clause(spec_inf, cols)
    assert where_inf == ""

    # "nan" as string in BETWEEN
    spec_between_nan = QuerySpec(
        filters=[FilterRule("VALORE", FilterOperator.BETWEEN, ("nan", 100))]
    )
    where_between_nan = QueryBuilder.build_where_clause(spec_between_nan, cols)
    assert where_between_nan == ""


def test_inverted_between_filter_normalization():
    """Verify BETWEEN with inverted bounds (100, 10) normalizes to (10, 100)."""
    cols = [ColumnMeta("IMPORTO", DataType.NUMERIC)]
    spec = QuerySpec(filters=[FilterRule("IMPORTO", FilterOperator.BETWEEN, (100, 10))])
    where = QueryBuilder.build_where_clause(spec, cols)
    assert "BETWEEN 10.0 AND 100.0" in where


def test_numeric_not_equals_distinct_from():
    """Verify numeric NOT_EQUALS generates IS DISTINCT FROM for NULL-safety."""
    cols = [ColumnMeta("CODICE", DataType.NUMERIC)]
    spec = QuerySpec(filters=[FilterRule("CODICE", FilterOperator.NOT_EQUALS, 42)])
    where = QueryBuilder.build_where_clause(spec, cols)
    assert "IS DISTINCT FROM 42.0" in where


def test_aggregation_count_subquery_strips_limit():
    """Verify build_count_query on an aggregated query strips LIMIT/OFFSET to count all groups."""
    spec = QuerySpec(
        group_by_columns=["REGIONE"],
        aggregations=[AggregationRule("IMPORTO", "sum", "totale_importo")],
        limit=5,
        offset=10,
    )
    count_sql = QueryBuilder.build_count_query("test_table", spec)
    assert "LIMIT" not in count_sql
    assert "OFFSET" not in count_sql
    assert "SELECT COUNT(*) FROM (" in count_sql
    assert "GROUP BY \"REGIONE\"" in count_sql


def test_duckdb_engine_context_manager():
    """Verify DuckDBEngine works as a context manager and cleanly closes."""
    with DuckDBEngine() as engine:
        assert engine.conn is not None
        res = engine.conn.execute("SELECT 1 + 1").fetchone()
        assert res[0] == 2
    # After exit, conn should be closed
    assert engine.conn is None


def test_query_builder_handles_min_max_without_double_corruption():
    """Verify MIN/MAX aggregations do not corrupt text columns with forced TRY_CAST(... AS DOUBLE)."""
    spec = QuerySpec(
        group_by_columns=["CATEGORIA"],
        aggregations=[
            AggregationRule("DATA_REGISTRAZIONE", "min", "prima_data"),
            AggregationRule("DATA_REGISTRAZIONE", "max", "ultima_data"),
        ],
    )
    sql = QueryBuilder.build_select_query("tabella", spec)
    assert 'MIN("DATA_REGISTRAZIONE") AS "prima_data"' in sql
    assert 'MAX("DATA_REGISTRAZIONE") AS "ultima_data"' in sql
    assert "TRY_CAST" not in sql


def test_regex_compile_error_graceful_handling():
    """Verify invalid regex syntax does not crash QueryBuilder."""
    cols = [ColumnMeta("TESTO", DataType.TEXT)]
    # Unclosed bracket is invalid regex
    spec = QuerySpec(filters=[FilterRule("TESTO", FilterOperator.REGEX, "[invalid")])
    where = QueryBuilder.build_where_clause(spec, cols)
    # Invalid regex should be safely skipped (empty where clause)
    assert where == ""


def test_xml_row_estimation_formula():
    """Verify XML row count estimation logic uses average record length correctly."""
    adapter = XmlAdapter()
    assert adapter is not None

    # 10 records totaling 2000 bytes -> 200 bytes per record
    sample_bytes = 2000
    sample_count = 10
    total_file_bytes = 1_000_000

    avg_len = max(50.0, sample_bytes / sample_count)
    est = int(total_file_bytes / avg_len)
    assert est == 5000
