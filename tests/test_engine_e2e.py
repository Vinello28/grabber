"""
End-to-end integration test verifying DuckDB analytical engine
with real datasets, streaming queries, and memory boundaries.
"""

import os

import psutil

from src.core.models import (
    AggregationFunc,
    AggregationRule,
    FilterOperator,
    FilterRule,
    QuerySpec,
)
from src.engine.duckdb_engine import DuckDBEngine


def test_e2e_csv_test1_queries_and_export():
    process = psutil.Process(os.getpid())
    initial_rss = process.memory_info().rss / (1024 * 1024)

    engine = DuckDBEngine(memory_limit="2GB")
    schema = engine.connect_dataset("data/test1")

    assert schema.source_format == "csv"
    assert len(schema.columns) == 27

    # 1. Test filtered search (Codice Fiscale)
    spec_filter = QuerySpec(
        filters=[
            FilterRule(
                column="CODICE_FISCALE_BENEFICIARIO",
                operator=FilterOperator.EQUALS,
                value="01263420778",
            )
        ],
        limit=10,
    )
    res_filter = engine.execute_query(spec_filter)
    assert res_filter.total_matching_rows == 19
    assert len(res_filter.rows) == 10
    assert res_filter.execution_time_seconds < 10.0

    # 2. Test Aggregation (Group by Regione)
    spec_agg = QuerySpec(
        group_by_columns=["REGIONE_BENEFICIARIO"],
        aggregations=[
            AggregationRule("*", AggregationFunc.COUNT, "totale_aiuti"),
        ],
        limit=5,
    )
    res_agg = engine.execute_query(spec_agg)
    assert len(res_agg.rows) == 5

    # 3. Test Streaming Export to CSV
    export_path = "exports/test_e2e_export.csv"
    exported_rows = engine.export_query(spec_filter, export_path, export_format="csv")
    assert exported_rows == 19
    assert os.path.exists(export_path)
    assert os.path.getsize(export_path) > 0

    # Clean up exported test file
    if os.path.exists(export_path):
        os.remove(export_path)

    # 4. Verify Memory Safety (RSS delta must stay under 2 GB even after querying 13.5GB dataset)
    final_rss = process.memory_info().rss / (1024 * 1024)
    rss_diff = final_rss - initial_rss
    print(f"E2E Test Memory RSS: Initial={initial_rss:.1f} MB, Final={final_rss:.1f} MB, Delta={rss_diff:.1f} MB")
    assert final_rss < 3072.0 and rss_diff <= 2048.0, f"Memory RSS exceeded safe threshold: {final_rss} MB (delta: {rss_diff} MB)"


def test_engine_view_lifecycle_recovery():
    """Verify that if the view is lost or dropped, ensure_view_exists recreates it seamlessly."""
    engine = DuckDBEngine(memory_limit="2GB")
    engine.connect_dataset("data/test1")
    assert engine.has_active_view() is True

    # Intentionally drop the view to simulate session/cache desync
    engine.conn.execute("DROP VIEW current_dataset")
    assert engine.has_active_view() is False

    # Executing query should not fail with Catalog Error, but recreate the view automatically
    spec = QuerySpec(
        filters=[FilterRule("REGIONE_BENEFICIARIO", FilterOperator.EQUALS, "Lombardia")],
        limit=5,
    )
    res = engine.execute_query(spec)
    assert len(res.rows) == 5
    assert engine.has_active_view() is True

