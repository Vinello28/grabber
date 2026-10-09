"""
Tests for multi-term search (comma-separated) and AND / OR boolean logic.
"""

from src.core.models import (
    BooleanOperator,
    ColumnMeta,
    DataType,
    FilterOperator,
    FilterRule,
    QuerySpec,
)
from src.engine.duckdb_engine import DuckDBEngine
from src.engine.query_builder import QueryBuilder


class TestParseSearchTokens:
    def test_comma_separated_tokens(self):
        text = "Roma, Milano, Napoli"
        tokens = QueryBuilder.parse_search_tokens(text)
        assert tokens == ["Roma", "Milano", "Napoli"]

    def test_multi_word_tokens_with_comma(self):
        text = "Mario Rossi, Luigi Verdi"
        tokens = QueryBuilder.parse_search_tokens(text)
        assert tokens == ["Mario Rossi", "Luigi Verdi"]

    def test_space_separated_fallback_when_no_comma(self):
        text = "Roma Milano"
        tokens = QueryBuilder.parse_search_tokens(text)
        assert tokens == ["Roma", "Milano"]

    def test_smart_and_straight_quotes_stripped(self):
        text = "“Milano”, 'Roma', «Napoli», \"Torino\""
        tokens = QueryBuilder.parse_search_tokens(text)
        assert tokens == ["Milano", "Roma", "Napoli", "Torino"]

    def test_empty_and_whitespace_only(self):
        assert QueryBuilder.parse_search_tokens("") == []
        assert QueryBuilder.parse_search_tokens("   ") == []
        assert QueryBuilder.parse_search_tokens(", , ,") == []


class TestQueryBuilderMultiTermAndBooleanLogic:
    def test_contains_multi_term_or_logic(self):
        rule = FilterRule(
            column="città",
            operator=FilterOperator.CONTAINS,
            value="Roma, Milano",
            term_logic=BooleanOperator.OR,
        )
        spec = QuerySpec(filters=[rule])
        where = QueryBuilder.build_where_clause(spec)
        assert "OR" in where
        assert "LOWER(CAST(\"città\" AS VARCHAR)) LIKE '%roma%'" in where
        assert "LOWER(CAST(\"città\" AS VARCHAR)) LIKE '%milano%'" in where

    def test_contains_multi_term_and_logic(self):
        rule = FilterRule(
            column="descrizione",
            operator=FilterOperator.CONTAINS,
            value="progetto, software",
            term_logic=BooleanOperator.AND,
        )
        spec = QuerySpec(filters=[rule])
        where = QueryBuilder.build_where_clause(spec)
        assert "AND" in where
        assert "LOWER(CAST(\"descrizione\" AS VARCHAR)) LIKE '%progetto%'" in where
        assert "LOWER(CAST(\"descrizione\" AS VARCHAR)) LIKE '%software%'" in where

    def test_not_contains_multi_term_and_logic(self):
        rule = FilterRule(
            column="tag",
            operator=FilterOperator.NOT_CONTAINS,
            value="bozza, test",
            term_logic=BooleanOperator.AND,
        )
        spec = QuerySpec(filters=[rule])
        where = QueryBuilder.build_where_clause(spec)
        assert "NOT LIKE '%bozza%'" in where
        assert "NOT LIKE '%test%'" in where
        assert "AND" in where

    def test_filter_battery_combination_or(self):
        rule1 = FilterRule(column="regione", operator=FilterOperator.EQUALS, value="Veneto")
        rule2 = FilterRule(column="regione", operator=FilterOperator.EQUALS, value="Lombardia")
        spec = QuerySpec(filters=[rule1, rule2], filter_logic=BooleanOperator.OR)
        where = QueryBuilder.build_where_clause(spec)
        assert "WHERE (LOWER(CAST(\"regione\" AS VARCHAR)) = 'veneto' OR LOWER(CAST(\"regione\" AS VARCHAR)) = 'lombardia')" in where

    def test_filter_battery_combination_and(self):
        rule1 = FilterRule(column="regione", operator=FilterOperator.EQUALS, value="Veneto")
        rule2 = FilterRule(column="settore", operator=FilterOperator.EQUALS, value="Edilizia")
        spec = QuerySpec(filters=[rule1, rule2], filter_logic=BooleanOperator.AND)
        where = QueryBuilder.build_where_clause(spec)
        assert "WHERE LOWER(CAST(\"regione\" AS VARCHAR)) = 'veneto' AND LOWER(CAST(\"settore\" AS VARCHAR)) = 'edilizia'" in where

    def test_global_search_multi_term_or(self):
        cols = [
            ColumnMeta(name="titolo", data_type=DataType.TEXT),
            ColumnMeta(name="note", data_type=DataType.TEXT),
        ]
        spec = QuerySpec(
            global_search="Milano, Torino",
            global_search_columns=["titolo", "note"],
            global_search_logic=BooleanOperator.OR,
        )
        where = QueryBuilder.build_where_clause(spec, schema_columns=cols)
        assert "milano" in where
        assert "torino" in where
        # Inside each column, OR between terms
        assert "(LOWER(CAST(\"titolo\" AS VARCHAR)) LIKE '%milano%' OR LOWER(CAST(\"titolo\" AS VARCHAR)) LIKE '%torino%')" in where

    def test_global_search_with_filter_battery_or(self):
        spec = QuerySpec(
            global_search="Roma",
            global_search_columns=["città"],
            filters=[
                FilterRule(column="tipo", operator=FilterOperator.EQUALS, value="A"),
                FilterRule(column="tipo", operator=FilterOperator.EQUALS, value="B"),
            ],
            filter_logic=BooleanOperator.OR,
        )
        where = QueryBuilder.build_where_clause(spec)
        assert where.startswith("WHERE")
        assert "LIKE '%roma%'" in where
        assert "AND" in where
        assert "(LOWER(CAST(\"tipo\" AS VARCHAR)) = 'a' OR LOWER(CAST(\"tipo\" AS VARCHAR)) = 'b')" in where


class TestDuckDBEngineMultiTermExecution:
    def test_in_memory_multi_term_and_filter_logic(self):
        engine = DuckDBEngine()
        # Seed an in-memory table
        engine.conn.execute("""
            CREATE TABLE test_multi_table (
                id INTEGER,
                città VARCHAR,
                categoria VARCHAR,
                importo DOUBLE
            );
            INSERT INTO test_multi_table VALUES
                (1, 'Roma Centro', 'Servizi', 100.0),
                (2, 'Milano Nord', 'Commercio', 200.0),
                (3, 'Napoli Porto', 'Servizi', 300.0),
                (4, 'Torino Centro', 'Industria', 400.0);
        """)
        engine.current_sql_source = "test_multi_table"
        from src.core.models import DatasetSchema
        engine.current_schema = DatasetSchema(
            source_path=":memory:",
            source_format="duckdb",
            columns=[
                ColumnMeta(name="id", data_type=DataType.NUMERIC, native_type="INTEGER"),
                ColumnMeta(name="città", data_type=DataType.TEXT, native_type="VARCHAR"),
                ColumnMeta(name="categoria", data_type=DataType.TEXT, native_type="VARCHAR"),
                ColumnMeta(name="importo", data_type=DataType.NUMERIC, native_type="DOUBLE"),
            ],
            table_identifier="test_multi_table",
        )

        # 1. Multi-term CONTAINS with OR: "Roma, Milano" -> should return 2 rows
        spec_or = QuerySpec(
            filters=[
                FilterRule(
                    column="città",
                    operator=FilterOperator.CONTAINS,
                    value="Roma, Milano",
                    term_logic=BooleanOperator.OR,
                )
            ]
        )
        res_or = engine.execute_query(spec_or)
        assert res_or.total_matching_rows == 2
        ids = [row[0] for row in res_or.rows]
        assert set(ids) == {1, 2}

        # 2. Multi-term CONTAINS with AND: "Roma, Milano" -> should return 0 rows
        spec_and = QuerySpec(
            filters=[
                FilterRule(
                    column="città",
                    operator=FilterOperator.CONTAINS,
                    value="Roma, Milano",
                    term_logic=BooleanOperator.AND,
                )
            ]
        )
        res_and = engine.execute_query(spec_and)
        assert res_and.total_matching_rows == 0

        # 3. Multi-term CONTAINS with AND on matching tokens: "Roma, Centro" -> should return 1 row (id 1)
        spec_match = QuerySpec(
            filters=[
                FilterRule(
                    column="città",
                    operator=FilterOperator.CONTAINS,
                    value="Roma, Centro",
                    term_logic=BooleanOperator.AND,
                )
            ]
        )
        res_match = engine.execute_query(spec_match)
        assert res_match.total_matching_rows == 1
        assert res_match.rows[0][0] == 1

        # 4. Filter battery with OR: categoria = 'Servizi' OR importo >= 400 -> rows 1, 3 (Servizi) + 4 (400) = 3 rows
        spec_filter_or = QuerySpec(
            filters=[
                FilterRule(column="categoria", operator=FilterOperator.EQUALS, value="Servizi"),
                FilterRule(column="importo", operator=FilterOperator.GTE, value=400),
            ],
            filter_logic=BooleanOperator.OR,
        )
        res_filter_or = engine.execute_query(spec_filter_or)
        assert res_filter_or.total_matching_rows == 3
        ids_or = [row[0] for row in res_filter_or.rows]
        assert set(ids_or) == {1, 3, 4}

        # 5. Same filters with AND -> 0 rows (Servizi has amounts 100, 300; none >= 400)
        spec_filter_and = QuerySpec(
            filters=[
                FilterRule(column="categoria", operator=FilterOperator.EQUALS, value="Servizi"),
                FilterRule(column="importo", operator=FilterOperator.GTE, value=400),
            ],
            filter_logic=BooleanOperator.AND,
        )
        res_filter_and = engine.execute_query(spec_filter_and)
        assert res_filter_and.total_matching_rows == 0

        engine.close()
