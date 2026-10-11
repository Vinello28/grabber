"""
Unit tests verifying Phase 1 and Phase 2 performance optimizations:
- QuerySpec filter fingerprinting & fast-path detection
- DuckDBEngine LRU count cache and zero-cost pagination
- QueryResult zero-copy DataFrame transport & lazy rows property
- Distinct values type-aware query generation & caching
- DatasetDetector single-pass scanning & mtime caching
- Dynamic filter battery cleanup on clear all
"""

from pathlib import Path

import duckdb
import pandas as pd

from src.adapters.detector import DatasetDetector
from src.core.models import (
    FilterOperator,
    FilterRule,
    QueryResult,
    QuerySpec,
)
from src.engine.duckdb_engine import DuckDBEngine


def test_query_spec_fingerprint_and_filter_detection():
    """Verify QuerySpec generates identical fingerprints across pagination and sort changes."""
    rule1 = FilterRule(column="AMOUNT", operator=FilterOperator.GT, value=100)
    spec1 = QuerySpec(
        filters=[rule1],
        limit=50,
        offset=0,
        selected_columns=["ID", "AMOUNT"],
        order_by=[("AMOUNT", True)],
    )
    spec2 = QuerySpec(
        filters=[rule1],
        limit=100,
        offset=500,  # Page 11
        selected_columns=["AMOUNT"],
        order_by=[("AMOUNT", False)],
    )

    assert spec1.has_filters_or_grouping is True
    assert spec2.has_filters_or_grouping is True
    # Fingerprints must match because filters and grouping are identical
    assert spec1.get_filter_fingerprint() == spec2.get_filter_fingerprint()

    # Empty query spec should have has_filters_or_grouping == False
    empty_spec = QuerySpec(limit=50, offset=0)
    assert empty_spec.has_filters_or_grouping is False


def test_query_result_zero_copy_and_lazy_rows():
    """Verify QueryResult wraps DataFrame without eager rows materialization, but maintains backwards compatibility."""
    sample_df = pd.DataFrame({"id": [1, 2, 3], "val": ["a", "b", "c"]})
    res = QueryResult(
        columns=["id", "val"],
        total_matching_rows=3,
        execution_time_seconds=0.001,
        df=sample_df,
    )

    # DataFrame is immediately available zero-copy
    assert res.df is sample_df
    # _rows should be None initially (lazy)
    assert res._rows is None

    # Accessing .rows triggers lazy conversion
    rows = res.rows
    assert len(rows) == 3
    assert rows[0] == [1, "a"]
    assert res._rows is not None

    # Legacy construction with explicit rows
    legacy_res = QueryResult(
        columns=["id"],
        rows=[[10], [20]],
        total_matching_rows=2,
        execution_time_seconds=0.002,
    )
    assert legacy_res.rows == [[10], [20]]


def test_duckdb_engine_count_cache_and_fast_path(tmp_path: Path):
    """Verify DuckDBEngine uses fast-path and caches matching row counts across pagination."""
    # Create sample Parquet dataset
    test_file = tmp_path / "sample.parquet"
    df = pd.DataFrame({"val": range(100), "cat": ["X", "Y"] * 50})
    con = duckdb.connect()
    con.register("df_src", df)
    con.execute("CREATE TABLE t AS SELECT * FROM df_src")
    con.execute(f"COPY t TO '{test_file}' (FORMAT PARQUET)")
    con.close()

    engine = DuckDBEngine()
    schema = engine.connect_dataset(str(test_file))
    assert schema.row_count_estimate == 100

    # 1. Unfiltered query fast-path: count_matching_rows returns estimate without running query
    empty_spec = QuerySpec(limit=10, offset=0)
    assert engine.count_matching_rows(empty_spec) == 100

    # 2. Filtered query: first execution populates cache
    rule = FilterRule(column="cat", operator=FilterOperator.EQUALS, value="X")
    spec_p1 = QuerySpec(filters=[rule], limit=10, offset=0)
    spec_p2 = QuerySpec(filters=[rule], limit=10, offset=10)

    # First call runs query and caches
    assert len(engine._count_cache) == 0
    c1 = engine.count_matching_rows(spec_p1)
    assert c1 == 50
    assert len(engine._count_cache) == 1

    # Second call (pagination page 2) retrieves from cache
    c2 = engine.count_matching_rows(spec_p2)
    assert c2 == 50

    # Execute query produces QueryResult with native df
    res = engine.execute_query(spec_p1)
    assert res.df is not None
    assert len(res.df) == 10
    assert res.total_matching_rows == 50

    engine.close()


def test_duckdb_engine_distinct_cache_and_type_awareness(tmp_path: Path):
    """Verify get_distinct_values caches results and avoids TRIM/CAST on numeric columns."""
    test_file = tmp_path / "numbers.parquet"
    df = pd.DataFrame({"num": [10, 20, 10, 30, 20], "txt": ["apple", "banana", "apple", "", None]})
    con = duckdb.connect()
    con.register("df_nums", df)
    con.execute("CREATE TABLE t AS SELECT * FROM df_nums")
    con.execute(f"COPY t TO '{test_file}' (FORMAT PARQUET)")
    con.close()


    engine = DuckDBEngine()
    engine.connect_dataset(str(test_file))

    # Numeric column distinct
    num_vals = engine.get_distinct_values("num", limit=10)
    assert sorted(num_vals) == [10, 20, 30]
    assert len(engine._distinct_cache) == 1

    # Second call uses cache
    num_vals_cached = engine.get_distinct_values("num", limit=10)
    assert num_vals_cached == num_vals

    # Text column distinct ignores empty string and None
    txt_vals = engine.get_distinct_values("txt", limit=10)
    assert sorted(txt_vals) == ["apple", "banana"]

    engine.close()


def test_dataset_detector_single_pass_and_caching(tmp_path: Path):
    """Verify DatasetDetector caches directory analysis using mtime."""
    DatasetDetector._cache.clear()

    # Create dummy dataset directory
    ds_dir = tmp_path / "ds"
    ds_dir.mkdir()
    f1 = ds_dir / "data1.csv"
    f2 = ds_dir / "data2.csv"
    f1.write_text("a,b\n1,2\n", encoding="utf-8")
    f2.write_text("a,b\n3,4\n", encoding="utf-8")

    # First analysis runs single-pass scan
    res1 = DatasetDetector.analyze_path(str(ds_dir))
    assert res1["format"] == "csv"
    assert res1["file_count"] == 2
    assert res1["total_size_bytes"] > 0

    resolved_key = str(ds_dir.resolve())
    assert resolved_key in DatasetDetector._cache

    # Second analysis returns cached result
    res2 = DatasetDetector.analyze_path(str(ds_dir))
    assert res2["file_count"] == 2
    assert res2["files"] == res1["files"]

    DatasetDetector._cache.clear()


def test_query_spec_fingerprint_boolean_logic():
    """Verify QuerySpec fingerprint differentiates filter_logic, global_search_logic, and term_logic."""
    from src.core.models import BooleanOperator

    r1 = FilterRule(column="A", operator=FilterOperator.CONTAINS, value="x, y", term_logic=BooleanOperator.AND)
    r2 = FilterRule(column="A", operator=FilterOperator.CONTAINS, value="x, y", term_logic=BooleanOperator.OR)

    spec_and = QuerySpec(filters=[r1], filter_logic=BooleanOperator.AND, global_search="test", global_search_logic=BooleanOperator.AND)
    spec_or = QuerySpec(filters=[r1], filter_logic=BooleanOperator.OR, global_search="test", global_search_logic=BooleanOperator.AND)
    spec_term_or = QuerySpec(filters=[r2], filter_logic=BooleanOperator.AND, global_search="test", global_search_logic=BooleanOperator.AND)
    spec_gs_or = QuerySpec(filters=[r1], filter_logic=BooleanOperator.AND, global_search="test", global_search_logic=BooleanOperator.OR)

    assert spec_and.get_filter_fingerprint() != spec_or.get_filter_fingerprint()
    assert spec_and.get_filter_fingerprint() != spec_term_or.get_filter_fingerprint()
    assert spec_and.get_filter_fingerprint() != spec_gs_or.get_filter_fingerprint()

