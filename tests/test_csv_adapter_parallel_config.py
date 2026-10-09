"""
Tests for CsvAdapter and DuckDBEngine handling of CSV files:
1. Multi-threaded parallel scanner active by default for clean datasets.
2. Transparent dynamic fallback to parallel=false only when quoted newlines conflict with null_padding.
3. Reset of parallel scanner to multi-threaded default when switching datasets.
"""

from pathlib import Path

import pytest

from src.adapters.csv_adapter import CsvAdapter
from src.core.models import QuerySpec
from src.engine.duckdb_engine import DuckDBEngine

REAL_CSV_PATH = Path("/home/gabs/Documenti/Università/AI nelle Imprese/open-data-analytics/data/classified_multiclass_aiuti_2016.csv")


def test_csv_adapter_build_sql_source_default_keeps_parallel_active():
    """Verify build_sql_source leaves parallel scanner active (not disabled) by default."""
    adapter = CsvAdapter()
    sql = adapter.build_sql_source("sample.csv", delim=",")
    assert "parallel=false" not in sql
    assert "null_padding=true" in sql
    assert "union_by_name=true" in sql


def test_csv_adapter_build_sql_source_explicit_parallel_options():
    """Verify build_sql_source respects explicit parallel flag."""
    adapter = CsvAdapter(parallel=True)
    sql_true = adapter.build_sql_source("sample.csv", delim=",")
    assert "parallel=true" in sql_true

    adapter_false = CsvAdapter(parallel=False)
    sql_false = adapter_false.build_sql_source("sample.csv", delim=",")
    assert "parallel=false" in sql_false

    # Override in method call
    adapter_default = CsvAdapter()
    sql_override = adapter_default.build_sql_source("sample.csv", delim=",", parallel=False)
    assert "parallel=false" in sql_override


def test_clean_csv_uses_parallel_without_fallback(tmp_path: Path):
    """Verify clean CSV files use parallel reader without triggering sequential fallback."""
    csv_file = tmp_path / "clean_data.csv"
    lines = ["id,name,score"]
    for i in range(100):
        lines.append(f"{i},user_{i},{i * 1.5}")
    csv_file.write_text("\n".join(lines), encoding="utf-8")

    engine = DuckDBEngine()
    schema = engine.connect_dataset(str(csv_file))
    assert schema.row_count_estimate == 100
    # Engine's csv_adapter should NOT have fallen back to False
    assert engine.csv_adapter.parallel is not False

    res = engine.execute_query(QuerySpec(limit=10))
    assert len(res.rows) == 10
    assert engine.csv_adapter.parallel is not False


def test_fallback_csv_to_sequential_helper(tmp_path: Path):
    """Verify _fallback_csv_to_sequential_if_needed correctly reconfigures view and adapter."""
    csv_file = tmp_path / "dummy.csv"
    csv_file.write_text("id,val\n1,a\n", encoding="utf-8")

    engine = DuckDBEngine()
    engine.connect_dataset(str(csv_file))
    assert engine.csv_adapter.parallel is None

    # Simulate error
    simulated_err = Exception("CSV Error: The parallel scanner does not support null_padding in conjunction with quoted new lines. Please disable the parallel csv reader with parallel=false")
    handled = engine._fallback_csv_to_sequential_if_needed(simulated_err)
    assert handled is True
    assert engine.csv_adapter.parallel is False
    assert "parallel=false" in (engine.current_sql_source or "")

    # Non-conflict error should NOT trigger fallback
    other_err = Exception("Syntax error in query")
    assert engine._fallback_csv_to_sequential_if_needed(other_err) is False


def test_real_multiclass_aiuti_2016_dynamic_fallback():
    """Verify real dataset triggers transparent fallback to parallel=false and executes correctly."""
    if not REAL_CSV_PATH.exists():
        pytest.skip(f"Test file not found: {REAL_CSV_PATH}")

    engine = DuckDBEngine()
    schema = engine.connect_dataset(str(REAL_CSV_PATH))
    assert schema.row_count_estimate == 8378
    assert len(schema.columns) == 25
    # Transparent fallback was activated
    assert engine.csv_adapter.parallel is False

    # Execute queries and check that everything works smoothly
    result = engine.execute_query(QuerySpec(limit=25))
    assert len(result.rows) == 25
    assert result.total_matching_rows == 8378

    count = engine.count_matching_rows(QuerySpec())
    assert count == 8378

    distincts = engine.get_distinct_values("TITOLO_MISURA", limit=5)
    assert len(distincts) > 0


def test_dataset_switch_resets_parallel_scanner(tmp_path: Path):
    """Verify switching from a problematic dataset to a clean dataset re-enables parallel scanning."""
    if not REAL_CSV_PATH.exists():
        pytest.skip(f"Test file not found: {REAL_CSV_PATH}")

    engine = DuckDBEngine()

    # 1. Load problematic dataset (triggers fallback to parallel=False)
    engine.connect_dataset(str(REAL_CSV_PATH))
    assert engine.csv_adapter.parallel is False

    # 2. Switch to clean dataset
    clean_csv = tmp_path / "clean_switch.csv"
    clean_csv.write_text("col_a,col_b\n1,hello\n2,world\n", encoding="utf-8")

    schema_clean = engine.connect_dataset(str(clean_csv))
    assert schema_clean.row_count_estimate == 2
    # parallel must be reset to None (multi-threaded parallel reader enabled)
    assert engine.csv_adapter.parallel is None

    res = engine.execute_query(QuerySpec())
    assert len(res.rows) == 2
    assert engine.csv_adapter.parallel is None
