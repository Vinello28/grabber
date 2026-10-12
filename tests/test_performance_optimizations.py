"""
Tests verifying performance and memory footprint optimizations (Fase 30).
Validates:
1. QueryResult native Apache Arrow Table and lazy row_count / df / rows evaluation.
2. QueryBuilder count subquery optimization (stripping ORDER BY).
3. Type-aware IS_NULL and IS_NOT_NULL compilation for numeric columns.
4. Lazy Streamlit bootstrap proxy in desktop_entrypoint.
5. XmlAdapter direct PyArrow Table batch writing.
"""

import pyarrow as pa
import pyarrow.parquet as pq

from desktop_entrypoint import _BootstrapProxy
from src.adapters.xml_adapter import XmlAdapter
from src.core.models import (
    AggregationRule,
    ColumnMeta,
    DataType,
    FilterOperator,
    FilterRule,
    QueryResult,
    QuerySpec,
)
from src.engine.query_builder import QueryBuilder


def test_query_result_arrow_table_and_lazy_evaluation():
    """Verify QueryResult wraps Arrow table zero-copy and computes row_count without materializing rows."""
    table = pa.table({"id": [1, 2, 3], "name": ["a", "b", "c"]})
    res = QueryResult(
        columns=["id", "name"],
        table=table,
        total_matching_rows=3,
    )

    # row_count should not trigger df or rows materialization
    assert res.row_count == 3
    assert res._df is None
    assert res._rows is None

    # Accessing .df lazily converts table to pandas
    df = res.df
    assert df is not None
    assert len(df) == 3
    assert res._df is not None
    assert res._rows is None  # rows still not materialized

    # Accessing .rows lazily converts df to list of lists
    rows = res.rows
    assert len(rows) == 3
    assert rows[0] == [1, "a"]
    assert res._rows is not None


def test_query_builder_count_subquery_strips_order_by():
    """Verify build_count_query on an aggregated query strips ORDER BY from the subquery."""
    spec = QuerySpec(
        group_by_columns=["REGIONE"],
        aggregations=[AggregationRule("IMPORTO", "sum", "totale_importo")],
        order_by=[("totale_importo", False)],
        limit=50,
        offset=100,
    )
    count_sql = QueryBuilder.build_count_query("dataset_table", spec)
    assert "ORDER BY" not in count_sql
    assert "LIMIT" not in count_sql
    assert "OFFSET" not in count_sql
    assert "SELECT COUNT(*) FROM (" in count_sql


def test_numeric_null_check_avoids_string_conversion():
    """Verify numeric IS_NULL and IS_NOT_NULL do not generate TRIM/CAST string checks."""
    cols = [ColumnMeta("IMPORTO", DataType.NUMERIC)]
    spec_null = QuerySpec(filters=[FilterRule("IMPORTO", FilterOperator.IS_NULL)])
    where_null = QueryBuilder.build_where_clause(spec_null, cols)
    assert '"IMPORTO" IS NULL' in where_null
    assert "TRIM(CAST(" not in where_null

    spec_not_null = QuerySpec(filters=[FilterRule("IMPORTO", FilterOperator.IS_NOT_NULL)])
    where_not_null = QueryBuilder.build_where_clause(spec_not_null, cols)
    assert '"IMPORTO" IS NOT NULL' in where_not_null
    assert "TRIM(CAST(" not in where_not_null


def test_text_null_check_maintains_empty_string_check():
    """Verify text IS_NULL checks include empty string comparison."""
    cols = [ColumnMeta("NOTE", DataType.TEXT)]
    spec_null = QuerySpec(filters=[FilterRule("NOTE", FilterOperator.IS_NULL)])
    where_null = QueryBuilder.build_where_clause(spec_null, cols)
    assert 'TRIM(CAST("NOTE" AS VARCHAR)) = \'\'' in where_null


def test_desktop_bootstrap_lazy_proxy():
    """Verify _BootstrapProxy delegates attribute access to streamlit.web.bootstrap."""
    proxy = _BootstrapProxy()
    # Check that getattr works on real methods of bootstrap
    assert callable(proxy.run)
    assert callable(proxy.load_config_options)


def test_xml_adapter_write_parquet_batch_direct_pylist(tmp_path):
    """Verify XmlAdapter writes parquet batches directly via PyArrow Table without Pandas."""
    adapter = XmlAdapter()
    batch = [
        {"ID": "1", "VAL": 10.5, "CAT": "A"},
        {"ID": "2", "VAL": 20.0, "CAT": "B"},
    ]
    adapter._write_parquet_batch(batch, tmp_path, file_idx=0, part_idx=0)
    out_file = tmp_path / "part_0000_0000.parquet"
    assert out_file.exists()

    # Read back and verify row count
    read_table = pq.read_table(out_file)
    assert read_table.num_rows == 2
    assert read_table.column_names == ["ID", "VAL", "CAT"]
