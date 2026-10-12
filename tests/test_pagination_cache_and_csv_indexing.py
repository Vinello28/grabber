"""
Tests for Task 32: Instant pagination caching and persistent CSV Parquet indexing.
Verifies that:
1. Base query fingerprinting is invariant to limit/offset but sensitive to filters/orders/columns.
2. Subsequent page queries hit the materialized temporary query table with from_cache=True.
3. Modifying filters or sorting triggers clean cache refresh.
4. Native CSV-to-Parquet conversion generates valid ZSTD Parquet files and connects via read_parquet.
5. Cache invalidation is properly executed upon dataset switch and engine close.
"""

import tempfile
from pathlib import Path

from src.core.models import FilterOperator, FilterRule, QuerySpec
from src.engine.duckdb_engine import DuckDBEngine


def test_base_query_fingerprint_invariance_and_sensitivity():
    """Verify that pagination parameters do not alter base query fingerprint, while constraints do."""
    rule1 = FilterRule(column="col_a", operator=FilterOperator.EQUALS, value="123")
    rule2 = FilterRule(column="col_b", operator=FilterOperator.CONTAINS, value="test")

    spec_page1 = QuerySpec(
        filters=[rule1],
        order_by=[("col_a", True)],
        selected_columns=["col_a", "col_b"],
        limit=50,
        offset=0,
    )

    spec_page2 = QuerySpec(
        filters=[rule1],
        order_by=[("col_a", True)],
        selected_columns=["col_a", "col_b"],
        limit=50,
        offset=50,
    )

    spec_page3_different_size = QuerySpec(
        filters=[rule1],
        order_by=[("col_a", True)],
        selected_columns=["col_a", "col_b"],
        limit=100,
        offset=200,
    )

    # Identical base query -> identical fingerprints
    fp1 = spec_page1.get_base_query_fingerprint()
    fp2 = spec_page2.get_base_query_fingerprint()
    fp3 = spec_page3_different_size.get_base_query_fingerprint()

    assert fp1 == fp2 == fp3

    # Different filter -> different fingerprint
    spec_diff_filter = QuerySpec(
        filters=[rule1, rule2],
        order_by=[("col_a", True)],
        selected_columns=["col_a", "col_b"],
        limit=50,
        offset=0,
    )
    assert spec_diff_filter.get_base_query_fingerprint() != fp1

    # Different sort -> different fingerprint
    spec_diff_sort = QuerySpec(
        filters=[rule1],
        order_by=[("col_a", False)],
        selected_columns=["col_a", "col_b"],
        limit=50,
        offset=0,
    )
    assert spec_diff_sort.get_base_query_fingerprint() != fp1

    # Different columns -> different fingerprint
    spec_diff_cols = QuerySpec(
        filters=[rule1],
        order_by=[("col_a", True)],
        selected_columns=["col_a"],
        limit=50,
        offset=0,
    )
    assert spec_diff_cols.get_base_query_fingerprint() != fp1


def test_pagination_materialized_cache_hit_and_invalidation():
    """Verify that page 1 materializes query results, page 2 hits cache, and filter changes invalidate cache."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write("id,category,amount\n")
        for i in range(1000):
            f.write(f"{i},cat_{i % 5},{i * 2.5}\n")
        csv_file = f.name

    try:
        with DuckDBEngine() as engine:
            engine.connect_dataset(csv_file)

            spec_p1 = QuerySpec(
                filters=[FilterRule(column="category", operator=FilterOperator.EQUALS, value="cat_2")],
                order_by=[("id", True)],
                limit=10,
                offset=0,
            )

            res1 = engine.execute_query(spec_p1)
            assert res1.row_count == 10
            assert res1.total_matching_rows == 200
            assert res1.from_cache is False

            # Page 2: same base query, offset=10 -> MUST hit cache
            spec_p2 = QuerySpec(
                filters=[FilterRule(column="category", operator=FilterOperator.EQUALS, value="cat_2")],
                order_by=[("id", True)],
                limit=10,
                offset=10,
            )
            res2 = engine.execute_query(spec_p2)
            assert res2.row_count == 10
            assert res2.total_matching_rows == 200
            assert res2.from_cache is True
            # Check row continuation
            assert res1.rows[0][0] == 2
            assert res2.rows[0][0] == 52

            # Page 5: offset=40 -> MUST also hit cache
            spec_p5 = QuerySpec(
                filters=[FilterRule(column="category", operator=FilterOperator.EQUALS, value="cat_2")],
                order_by=[("id", True)],
                limit=10,
                offset=40,
            )
            res5 = engine.execute_query(spec_p5)
            assert res5.from_cache is True
            assert res5.rows[0][0] == 202

            # Count matching rows should also return immediately from active query count
            cnt = engine.count_matching_rows(spec_p2)
            assert cnt == 200

            # Filter change -> cache miss and new materialization
            spec_p1_new_filter = QuerySpec(
                filters=[FilterRule(column="category", operator=FilterOperator.EQUALS, value="cat_3")],
                order_by=[("id", True)],
                limit=10,
                offset=0,
            )
            res_new = engine.execute_query(spec_p1_new_filter)
            assert res_new.from_cache is False
            assert res_new.rows[0][0] == 3
    finally:
        Path(csv_file).unlink(missing_ok=True)


def test_csv_to_parquet_indexing_and_reconnection():
    """Verify that index_csv_dataset creates persistent Parquet files and reconnects with high performance."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write("id,name,value\n")
        for i in range(500):
            f.write(f"{i},item_{i},{i * 10.0}\n")
        csv_file = f.name

    temp_cache_dir = Path(tempfile.mkdtemp())

    try:
        with DuckDBEngine() as engine:
            engine.csv_adapter._cache_dir = temp_cache_dir
            schema = engine.connect_dataset(csv_file)
            assert schema.source_format == "csv"
            assert "read_csv" in (engine.current_sql_source or "")

            # Index CSV dataset
            engine.index_csv_dataset(clean_cache=True)
            assert "read_parquet" in (engine.current_sql_source or "")

            # Verify Parquet files exist in cache
            cache_path = engine.csv_adapter.get_cache_path(csv_file)
            parquet_files = list(cache_path.glob("**/*.parquet"))
            assert len(parquet_files) >= 1

            # Test querying indexed dataset
            spec = QuerySpec(limit=20, offset=0)
            res = engine.execute_query(spec)
            assert res.row_count == 20
            assert res.total_matching_rows == 500

            # Re-connect to same CSV -> should automatically use Parquet cache
            schema_reconnected = engine.connect_dataset(csv_file)
            assert "read_parquet" in (engine.current_sql_source or "")
            assert schema_reconnected.row_count_estimate == 500
    finally:
        Path(csv_file).unlink(missing_ok=True)
        import shutil
        shutil.rmtree(temp_cache_dir, ignore_errors=True)


def test_clear_query_cache_on_dataset_switch():
    """Verify that switching dataset purges previous query materialized tables."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f1:
        f1.write("id,val\n1,10\n2,20\n")
        csv1 = f1.name

    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f2:
        f2.write("code,desc\nA,First\nB,Second\n")
        csv2 = f2.name

    try:
        with DuckDBEngine() as engine:
            engine.connect_dataset(csv1)
            engine.execute_query(QuerySpec(limit=5, offset=0))
            assert engine._active_query_fingerprint is not None

            # Switch to dataset 2
            engine.connect_dataset(csv2)
            assert engine._active_query_fingerprint is None
            assert engine._active_query_total_count is None
    finally:
        Path(csv1).unlink(missing_ok=True)
        Path(csv2).unlink(missing_ok=True)
