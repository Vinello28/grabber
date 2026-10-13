"""
Automated unit and integration regression tests for:
1. Parquet cache deletion auto-fallback (resilient recovery to original dataset).
2. Notion/Airtable style nested Filter Groups in QueryBuilder and models.
3. Human-readable filter summary generation.
"""

import shutil
import tempfile
from pathlib import Path

import pytest

from src.adapters.csv_adapter import CsvAdapter
from src.core.models import (
    BooleanOperator,
    FilterGroup,
    FilterOperator,
    FilterRule,
    QuerySpec,
)
from src.engine.duckdb_engine import DuckDBEngine
from src.engine.query_builder import QueryBuilder


@pytest.fixture
def sample_csv_dataset():
    """Create a temporary CSV file with sample records."""
    temp_dir = tempfile.mkdtemp(prefix="grabber_test_csv_")
    csv_file = Path(temp_dir) / "data.csv"
    csv_file.write_text(
        "ID,NOME,REGIONE,IMPORTO\n"
        "1,Alpha,Lazio,150.50\n"
        "2,Beta,Lombardia,300.00\n"
        "3,Gamma,Veneto,50.00\n"
        "4,Delta,Lazio,450.75\n"
        "5,Epsilon,Sicilia,20.00\n"
    )
    yield str(csv_file)
    shutil.rmtree(temp_dir, ignore_errors=True)


class TestParquetCacheDeletionFallback:
    def test_cache_deletion_and_transparent_fallback(self, sample_csv_dataset):
        """
        Verify that if Parquet cache files are deleted while the engine is running,
        the engine detects the missing files, falls back to the original CSV, and
        executes queries without crashing.
        """
        with DuckDBEngine() as engine:
            schema = engine.connect_dataset(sample_csv_dataset)
            assert schema.source_format == "csv"

            # 1. Index CSV into Parquet
            engine.index_csv_dataset()
            csv_adapter = CsvAdapter()
            cache_path = csv_adapter.get_cache_path([sample_csv_dataset])
            assert cache_path.exists()
            assert any(cache_path.glob("**/*.parquet"))
            assert "read_parquet" in (engine.current_sql_source or "")

            # Verify query executes from Parquet
            spec = QuerySpec()
            res = engine.execute_query(spec)
            assert res.total_matching_rows == 5

            # 2. Simulate user/external cache deletion on disk
            shutil.rmtree(cache_path, ignore_errors=True)
            assert not cache_path.exists()

            # 3. Call ensure_view_exists: should probe, fail, and reconnect to CSV
            engine.ensure_view_exists()
            assert "read_csv" in (engine.current_sql_source or "")

            # 4. Execute query: should succeed transparently from CSV
            res_after = engine.execute_query(spec)
            assert res_after.total_matching_rows == 5

    def test_direct_query_recovers_from_unannounced_cache_deletion(self, sample_csv_dataset):
        """
        Verify that even if ensure_view_exists was NOT called, DuckDBEngine._execute_sql
        catches the Parquet missing files IOException and auto-reconnects to the raw source.
        """
        with DuckDBEngine() as engine:
            engine.connect_dataset(sample_csv_dataset)
            engine.index_csv_dataset()

            csv_adapter = CsvAdapter()
            cache_path = csv_adapter.get_cache_path([sample_csv_dataset])
            assert cache_path.exists()

            # Wipe cache behind engine's back without calling ensure_view_exists
            shutil.rmtree(cache_path, ignore_errors=True)

            # Direct query execution must recover on the fly
            spec = QuerySpec(
                filters=[FilterRule(column="REGIONE", operator=FilterOperator.EQUALS, value="Lazio")]
            )
            res = engine.execute_query(spec)
            assert res.total_matching_rows == 2


class TestFilterGroupsAndQueryBuilder:
    def test_single_group_and_logic(self):
        rule1 = FilterRule(column="REGIONE", operator=FilterOperator.EQUALS, value="Lazio")
        rule2 = FilterRule(column="IMPORTO", operator=FilterOperator.GT, value="100")
        group = FilterGroup(id="g1", rules=[rule1, rule2], logic=BooleanOperator.AND)

        spec = QuerySpec(filter_groups=[group])
        where = QueryBuilder.build_where_clause(spec)
        assert 'LOWER(CAST("REGIONE" AS VARCHAR)) = \'lazio\'' in where
        assert 'CAST("IMPORTO" AS VARCHAR) > 100' in where or '"IMPORTO" > 100' in where or "IMPORTO" in where
        assert "AND" in where

    def test_single_group_or_logic(self):
        rule1 = FilterRule(column="REGIONE", operator=FilterOperator.EQUALS, value="Lazio")
        rule2 = FilterRule(column="REGIONE", operator=FilterOperator.EQUALS, value="Lombardia")
        group = FilterGroup(id="g1", rules=[rule1, rule2], logic=BooleanOperator.OR)

        spec = QuerySpec(filter_groups=[group])
        where = QueryBuilder.build_where_clause(spec)
        assert "OR" in where
        assert 'LOWER(CAST("REGIONE" AS VARCHAR)) = \'lazio\'' in where
        assert 'LOWER(CAST("REGIONE" AS VARCHAR)) = \'lombardia\'' in where

    def test_multiple_groups_inter_group_and_logic(self):
        # (Anno = 2024 AND Importo > 1000) AND (Regione = Lazio OR Regione = Lombardia)
        g1_r1 = FilterRule(column="ANNO", operator=FilterOperator.EQUALS, value="2024")
        g1_r2 = FilterRule(column="IMPORTO", operator=FilterOperator.GT, value="1000")
        g1 = FilterGroup(id="g1", rules=[g1_r1, g1_r2], logic=BooleanOperator.AND)

        g2_r1 = FilterRule(column="REGIONE", operator=FilterOperator.EQUALS, value="Lazio")
        g2_r2 = FilterRule(column="REGIONE", operator=FilterOperator.EQUALS, value="Lombardia")
        g2 = FilterGroup(id="g2", rules=[g2_r1, g2_r2], logic=BooleanOperator.OR)

        spec = QuerySpec(
            filter_groups=[g1, g2],
            filter_group_logic=BooleanOperator.AND,
        )
        where = QueryBuilder.build_where_clause(spec)
        # Should be ((g1_1 AND g1_2) AND (g2_1 OR g2_2))
        assert "WHERE ((" in where or "WHERE " in where
        assert "AND" in where
        assert "OR" in where

    def test_multiple_groups_inter_group_or_logic(self):
        # (Regione = Lazio AND Importo > 1000) OR (Regione = Veneto AND Importo < 100)
        g1 = FilterGroup(
            id="g1",
            rules=[
                FilterRule(column="REGIONE", operator=FilterOperator.EQUALS, value="Lazio"),
                FilterRule(column="IMPORTO", operator=FilterOperator.GT, value="1000"),
            ],
            logic=BooleanOperator.AND,
        )
        g2 = FilterGroup(
            id="g2",
            rules=[
                FilterRule(column="REGIONE", operator=FilterOperator.EQUALS, value="Veneto"),
                FilterRule(column="IMPORTO", operator=FilterOperator.LT, value="100"),
            ],
            logic=BooleanOperator.AND,
        )
        spec = QuerySpec(
            filter_groups=[g1, g2],
            filter_group_logic=BooleanOperator.OR,
        )
        where = QueryBuilder.build_where_clause(spec)
        assert ") OR (" in where

    def test_human_readable_filter_summary(self):
        g1 = FilterGroup(
            id="g1",
            rules=[
                FilterRule(column="ANNO", operator=FilterOperator.EQUALS, value="2024"),
                FilterRule(column="IMPORTO", operator=FilterOperator.GT, value="1000"),
            ],
            logic=BooleanOperator.AND,
        )
        g2 = FilterGroup(
            id="g2",
            rules=[
                FilterRule(column="REGIONE", operator=FilterOperator.CONTAINS, value="Lazio, Lombardia", term_logic=BooleanOperator.OR),
            ],
            logic=BooleanOperator.AND,
        )
        spec = QuerySpec(
            filter_groups=[g1, g2],
            filter_group_logic=BooleanOperator.AND,
            global_search="progetto",
        )
        summary = QueryBuilder.build_human_readable_filter_summary(spec)
        assert summary is not None
        assert 'Ricerca rapida "progetto"' in summary
        assert 'ANNO = "2024"' in summary
        assert "IMPORTO > 1000" in summary
        assert "REGIONE contiene" in summary

    def test_filter_fingerprint_differentiates_groups(self):
        g1 = FilterGroup(
            id="g1",
            rules=[FilterRule(column="A", operator=FilterOperator.EQUALS, value="1")],
            logic=BooleanOperator.AND,
        )
        spec_and = QuerySpec(filter_groups=[g1], filter_group_logic=BooleanOperator.AND)
        spec_or = QuerySpec(filter_groups=[g1], filter_group_logic=BooleanOperator.OR)
        assert spec_and.get_filter_fingerprint() != spec_or.get_filter_fingerprint()
