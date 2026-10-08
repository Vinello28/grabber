"""
Unit tests for SQL query builder and compiler.
"""

from src.core.models import (
    AggregationFunc,
    AggregationRule,
    ColumnMeta,
    DataType,
    FilterOperator,
    FilterRule,
    QuerySpec,
)
from src.engine.query_builder import QueryBuilder


def test_quote_ident():
    assert QueryBuilder.quote_ident("col_name") == '"col_name"'
    assert QueryBuilder.quote_ident('col"name') == '"col""name"'


def test_text_filters():
    cols = [ColumnMeta("NOME", DataType.TEXT)]
    
    # Contains
    spec = QuerySpec(filters=[FilterRule("NOME", FilterOperator.CONTAINS, "rossi")])
    where = QueryBuilder.build_where_clause(spec, cols)
    assert 'LOWER(CAST("NOME" AS VARCHAR)) LIKE \'%rossi%\'' in where

    # Starts with
    spec = QuerySpec(filters=[FilterRule("NOME", FilterOperator.STARTS_WITH, "mario")])
    where = QueryBuilder.build_where_clause(spec, cols)
    assert 'LOWER(CAST("NOME" AS VARCHAR)) LIKE \'mario%\'' in where

    # Equals
    spec = QuerySpec(filters=[FilterRule("NOME", FilterOperator.EQUALS, "VERDI")])
    where = QueryBuilder.build_where_clause(spec, cols)
    assert 'LOWER(CAST("NOME" AS VARCHAR)) = \'verdi\'' in where


def test_numeric_filters():
    cols = [ColumnMeta("VALORE", DataType.NUMERIC)]

    spec = QuerySpec(filters=[FilterRule("VALORE", FilterOperator.GTE, "100.5")])
    where = QueryBuilder.build_where_clause(spec, cols)
    assert 'TRY_CAST("VALORE" AS DOUBLE) >= 100.5' in where

    spec_btw = QuerySpec(filters=[FilterRule("VALORE", FilterOperator.BETWEEN, "10", value_to="50")])
    where_btw = QueryBuilder.build_where_clause(spec_btw, cols)
    assert 'TRY_CAST("VALORE" AS DOUBLE) BETWEEN 10.0 AND 50.0' in where_btw


def test_categorical_filter():
    cols = [ColumnMeta("REGIONE", DataType.CATEGORICAL)]
    spec = QuerySpec(filters=[FilterRule("REGIONE", FilterOperator.IN_LIST, ["Veneto", "Lazio"])])
    where = QueryBuilder.build_where_clause(spec, cols)
    assert 'CAST("REGIONE" AS VARCHAR) IN (\'Veneto\', \'Lazio\')' in where


def test_global_search():
    cols = [
        ColumnMeta("CF", DataType.TEXT),
        ColumnMeta("NOME", DataType.TEXT),
    ]
    spec = QuerySpec(global_search="RSSMRA")
    where = QueryBuilder.build_where_clause(spec, cols)
    assert 'LOWER(CAST("CF" AS VARCHAR)) LIKE \'%rssmra%\'' in where
    assert 'LOWER(CAST("NOME" AS VARCHAR)) LIKE \'%rssmra%\'' in where


def test_aggregated_query():
    cols = [
        ColumnMeta("REGIONE", DataType.CATEGORICAL),
        ColumnMeta("IMPORTO", DataType.NUMERIC),
    ]
    spec = QuerySpec(
        group_by_columns=["REGIONE"],
        aggregations=[
            AggregationRule("*", AggregationFunc.COUNT, "tot"),
            AggregationRule("IMPORTO", AggregationFunc.SUM, "somma"),
        ],
        limit=10,
    )
    sql = QueryBuilder.build_select_query("test_table", spec, cols)
    assert 'SELECT "REGIONE", COUNT(*) AS "tot", SUM(TRY_CAST("IMPORTO" AS DOUBLE)) AS "somma"' in sql
    assert 'FROM test_table' in sql
    assert 'GROUP BY "REGIONE"' in sql
    assert 'LIMIT 10' in sql
