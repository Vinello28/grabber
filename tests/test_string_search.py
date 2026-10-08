"""
Unit and integration tests for string search, quote sanitization,
multi-token search, and pagination offset recovery.
"""

import pytest
import duckdb
from src.core.models import (
    ColumnMeta,
    DataType,
    FilterOperator,
    FilterRule,
    QuerySpec,
    QueryResult,
)
from src.engine.query_builder import QueryBuilder
from src.engine.duckdb_engine import DuckDBEngine


def test_quote_and_whitespace_sanitization_in_filter():
    """Verify straight and smart/curly quotes and whitespace are stripped from text filter values."""
    col = ColumnMeta(name="DESCRIZIONE_PROGETTO", data_type=DataType.TEXT, native_type="VARCHAR")
    schema_cols = [col]

    test_inputs = [
        '"intelligenza"',
        "'intelligenza'",
        '“intelligenza”',
        '‘intelligenza’',
        '  intelligenza  ',
        '  "intelligenza"  ',
        '“intelligenza artificiale”',
    ]

    for val in test_inputs[:6]:
        rule = FilterRule(
            column="DESCRIZIONE_PROGETTO",
            operator=FilterOperator.CONTAINS,
            value=val,
        )
        spec = QuerySpec(filters=[rule])
        where = QueryBuilder.build_where_clause(spec, schema_cols)
        assert "intelligenza" in where
        assert '"intelligenza"' not in where
        assert "'\"" not in where
        assert "“" not in where
        assert "”" not in where
        assert "LOWER(CAST(\"DESCRIZIONE_PROGETTO\" AS VARCHAR)) LIKE '%intelligenza%'" in where


def test_multi_token_search_in_filter():
    """Verify multiple words in CONTAINS filter are compiled into AND-conjunction."""
    col = ColumnMeta(name="DESCRIZIONE_PROGETTO", data_type=DataType.TEXT, native_type="VARCHAR")
    rule = FilterRule(
        column="DESCRIZIONE_PROGETTO",
        operator=FilterOperator.CONTAINS,
        value="intelligenza artificiale",
    )
    spec = QuerySpec(filters=[rule])
    where = QueryBuilder.build_where_clause(spec, [col])
    assert "LIKE '%intelligenza%'" in where
    assert "LIKE '%artificiale%'" in where
    assert " AND " in where


def test_global_search_quote_and_multi_token():
    """Verify global search sanitizes quotes and handles multi-token search across columns."""
    cols = [
        ColumnMeta(name="TITOLO_PROGETTO", data_type=DataType.TEXT, native_type="VARCHAR"),
        ColumnMeta(name="DESCRIZIONE_PROGETTO", data_type=DataType.TEXT, native_type="VARCHAR"),
    ]
    spec = QuerySpec(global_search='“intelligenza artificiale”')
    where = QueryBuilder.build_where_clause(spec, cols)
    assert "“" not in where
    assert "”" not in where
    assert "intelligenza" in where
    assert "artificiale" in where


def test_in_memory_duckdb_string_search_execution():
    """Verify actual DuckDB execution with query builder against sample data."""
    conn = duckdb.connect(database=":memory:")
    conn.execute("""
        CREATE TABLE sample_ai (
            id INT,
            DESCRIZIONE_PROGETTO VARCHAR
        );
        INSERT INTO sample_ai VALUES
            (1, 'Sviluppo di una piattaforma di intelligenza artificiale per diagnosi medica'),
            (2, 'Ricerca applicata su algoritmi di machine learning e intelligenza'),
            (3, 'Impianto fotovoltaico industriale ad alta efficienza'),
            (4, 'Sistemi di automazione con integrazione di intelligenza e visione');
    """)

    cols = [
        ColumnMeta(name="id", data_type=DataType.NUMERIC, native_type="INT"),
        ColumnMeta(name="DESCRIZIONE_PROGETTO", data_type=DataType.TEXT, native_type="VARCHAR"),
    ]

    # Query with quotes in filter value
    rule = FilterRule(
        column="DESCRIZIONE_PROGETTO",
        operator=FilterOperator.CONTAINS,
        value='"intelligenza"',
    )
    spec = QuerySpec(filters=[rule])
    sql = QueryBuilder.build_select_query("sample_ai", spec, cols)
    df = conn.execute(sql).fetchdf()

    assert len(df) == 3
    assert set(df["id"].tolist()) == {1, 2, 4}


def test_pagination_offset_recovery():
    """Verify offset recovery logic when page offset exceeds matching results."""
    conn = duckdb.connect(database=":memory:")
    conn.execute("""
        CREATE TABLE test_recovery (id INT, txt VARCHAR);
        INSERT INTO test_recovery VALUES (1, 'intelligenza alfa'), (2, 'intelligenza beta');
    """)

    cols = [
        ColumnMeta(name="id", data_type=DataType.NUMERIC, native_type="INT"),
        ColumnMeta(name="txt", data_type=DataType.TEXT, native_type="VARCHAR"),
    ]

    # Suppose current_page was 5 with page_size 50, so offset was 200
    rule = FilterRule(column="txt", operator=FilterOperator.CONTAINS, value="intelligenza")
    initial_spec = QuerySpec(filters=[rule], limit=50, offset=200)

    # Count matching rows
    count_sql = QueryBuilder.build_count_query("test_recovery", initial_spec, cols)
    total_matching = conn.execute(count_sql).fetchone()[0]
    assert total_matching == 2

    # Query at offset 200 returns 0 rows
    sql_offset = QueryBuilder.build_select_query("test_recovery", initial_spec, cols)
    res_offset = conn.execute(sql_offset).fetchall()
    assert len(res_offset) == 0

    # UI recovery logic: since total_matching > 0 and len(rows) == 0, reset spec.offset = 0
    recovered_spec = QuerySpec(filters=[rule], limit=50, offset=0)
    sql_recovered = QueryBuilder.build_select_query("test_recovery", recovered_spec, cols)
    res_recovered = conn.execute(sql_recovered).fetchall()
    assert len(res_recovered) == 2


def test_duckdb_engine_drops_stale_view_on_unindexed_xml(tmp_path):
    """Verify DuckDBEngine drops the active view when an unindexed XML is loaded."""
    # Create a fresh isolated unindexed XML folder
    unindexed_dir = tmp_path / "fresh_unindexed_xml"
    unindexed_dir.mkdir()
    sample_xml = unindexed_dir / "sample.xml"
    sample_xml.write_text("<DATA><RECORD><ID>1</ID><TXT>test</TXT></RECORD></DATA>", encoding="utf-8")

    engine = DuckDBEngine()
    # First connect test1 (CSV)
    schema_csv = engine.connect_dataset("data/test1")
    assert engine.has_active_view()
    assert engine.current_sql_source is not None

    # Now connect unindexed XML
    schema_xml = engine.connect_dataset(str(unindexed_dir))
    # Verify stale view was dropped so queries don't inadvertently run against previous dataset
    assert not engine.has_active_view()
    assert engine.current_sql_source is None

    # ensure_view_exists should raise descriptive RuntimeError
    with pytest.raises(RuntimeError) as exc_info:
        engine.ensure_view_exists()
    assert "XML" in str(exc_info.value)
