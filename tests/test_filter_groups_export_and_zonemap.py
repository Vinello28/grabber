"""
Regression and unit test suite for Task 38:
- filter_groups preservation in export, count, and pagination queries
- Native numeric zonemap pushdown vs VARCHAR TRY_CAST
- Selective materialization of _active_query_cache
- Zero-copy PyArrow and fetchall schema inspection
"""

import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from src.adapters.parquet_adapter import ParquetAdapter
from src.core.models import (
    AggregationFunc,
    AggregationRule,
    BooleanOperator,
    ColumnMeta,
    DataType,
    FilterGroup,
    FilterOperator,
    FilterRule,
    QuerySpec,
)
from src.engine.duckdb_engine import DuckDBEngine
from src.engine.query_builder import QueryBuilder


def test_column_meta_has_native_numeric_type() -> None:
    """Verify ColumnMeta.has_native_numeric_type accurately distinguishes native numbers from strings/intervals."""
    col_bigint = ColumnMeta(name="id", data_type=DataType.NUMERIC, native_type="BIGINT")
    col_int = ColumnMeta(name="count", data_type=DataType.NUMERIC, native_type="INTEGER")
    col_double = ColumnMeta(name="price", data_type=DataType.NUMERIC, native_type="DOUBLE")
    col_decimal = ColumnMeta(name="amount", data_type=DataType.NUMERIC, native_type="DECIMAL(12,2)")
    col_interval = ColumnMeta(name="dur", data_type=DataType.NUMERIC, native_type="INTERVAL")
    col_varchar = ColumnMeta(name="raw_num", data_type=DataType.NUMERIC, native_type="VARCHAR")
    col_text = ColumnMeta(name="desc", data_type=DataType.TEXT, native_type="VARCHAR")

    assert col_bigint.has_native_numeric_type() is True
    assert col_int.has_native_numeric_type() is True
    assert col_double.has_native_numeric_type() is True
    assert col_decimal.has_native_numeric_type() is True
    assert col_interval.has_native_numeric_type() is False
    assert col_varchar.has_native_numeric_type() is False
    assert col_text.has_native_numeric_type() is False


def test_query_builder_zonemap_pushdown_vs_varchar() -> None:
    """Verify QueryBuilder omits TRY_CAST for native numeric columns and retains it for VARCHAR."""
    col_native = ColumnMeta(name="val_num", data_type=DataType.NUMERIC, native_type="DOUBLE")
    col_varchar = ColumnMeta(name="val_str", data_type=DataType.NUMERIC, native_type="VARCHAR")
    cols = [col_native, col_varchar]

    # Native GT
    spec_gt_native = QuerySpec(filters=[FilterRule(column="val_num", operator=FilterOperator.GT, value=100)])
    sql_native = QueryBuilder.build_where_clause(spec_gt_native, cols)
    assert sql_native == 'WHERE "val_num" > 100.0'
    assert "TRY_CAST" not in sql_native

    # VARCHAR GT (retains TRY_CAST)
    spec_gt_varchar = QuerySpec(filters=[FilterRule(column="val_str", operator=FilterOperator.GT, value=100)])
    sql_varchar = QueryBuilder.build_where_clause(spec_gt_varchar, cols)
    assert sql_varchar == 'WHERE TRY_CAST("val_str" AS DOUBLE) > 100.0'

    # Native EQUALS & NOT_EQUALS
    spec_eq_native = QuerySpec(filters=[FilterRule(column="val_num", operator=FilterOperator.EQUALS, value=50)])
    assert QueryBuilder.build_where_clause(spec_eq_native, cols) == 'WHERE "val_num" = 50.0'

    spec_ne_native = QuerySpec(filters=[FilterRule(column="val_num", operator=FilterOperator.NOT_EQUALS, value=50)])
    assert QueryBuilder.build_where_clause(spec_ne_native, cols) == 'WHERE "val_num" IS DISTINCT FROM 50.0'

    # Native BETWEEN
    spec_bt_native = QuerySpec(filters=[FilterRule(column="val_num", operator=FilterOperator.BETWEEN, value=10, value_to=20)])
    assert QueryBuilder.build_where_clause(spec_bt_native, cols) == 'WHERE "val_num" BETWEEN 10.0 AND 20.0'


def test_build_export_query_preserves_filter_groups() -> None:
    """Verify build_export_query does NOT lose filter_groups in generated COPY query."""
    group1 = FilterGroup(
        id="g1",
        rules=[FilterRule(column="Anno", operator=FilterOperator.EQUALS, value=2024)],
        logic=BooleanOperator.AND,
    )
    group2 = FilterGroup(
        id="g2",
        rules=[
            FilterRule(column="Regione", operator=FilterOperator.EQUALS, value="Lazio"),
            FilterRule(column="Regione", operator=FilterOperator.EQUALS, value="Lombardia"),
        ],
        logic=BooleanOperator.OR,
    )
    spec = QuerySpec(
        filter_groups=[group1, group2],
        filter_group_logic=BooleanOperator.AND,
        selected_columns=["Anno", "Regione", "Importo"],
        limit=50,  # Should be stripped in export
        offset=100,  # Should be stripped in export
    )

    csv_sql = QueryBuilder.build_export_query("current_dataset", spec, "/tmp/out.csv", export_format="csv")
    assert " LIMIT " not in csv_sql
    assert " OFFSET " not in csv_sql
    assert '"Anno"' in csv_sql
    assert '"Regione"' in csv_sql
    assert "lazio" in csv_sql
    assert "lombardia" in csv_sql
    assert "DELIMITER ','" in csv_sql

    parquet_sql = QueryBuilder.build_export_query("current_dataset", spec, "/tmp/out.parquet", export_format="parquet")
    assert "FORMAT PARQUET" in parquet_sql
    assert '"Anno"' in parquet_sql
    assert "lazio" in parquet_sql


def test_build_count_query_preserves_filter_groups_with_aggregations() -> None:
    """Verify build_count_query preserves filter_groups when calculating total groups."""
    group = FilterGroup(
        id="g1",
        rules=[FilterRule(column="Status", operator=FilterOperator.EQUALS, value="Active")],
        logic=BooleanOperator.AND,
    )
    spec = QuerySpec(
        filter_groups=[group],
        group_by_columns=["Regione"],
        aggregations=[AggregationRule(column="Importo", func=AggregationFunc.SUM, alias="tot_importo")],
        limit=10,
        offset=20,
    )

    count_sql = QueryBuilder.build_count_query("current_dataset", spec)
    assert 'LOWER(CAST("Status" AS VARCHAR)) = \'active\'' in count_sql
    assert " LIMIT " not in count_sql
    assert " OFFSET " not in count_sql
    assert "SELECT COUNT(*) FROM (" in count_sql


@pytest.fixture
def sample_dataset_path(tmp_path: Path) -> Path:
    """Create a sample CSV with 100 heterogeneous rows."""
    file_path = tmp_path / "data.csv"
    lines = ["Anno,Regione,Importo,Status\n"]
    for i in range(100):
        anno = 2024 if i % 2 == 0 else 2023
        regione = "Lazio" if i % 3 == 0 else ("Lombardia" if i % 3 == 1 else "Veneto")
        importo = 100.5 * (i + 1)
        status = "Active" if i % 4 == 0 else "Pending"
        lines.append(f"{anno},{regione},{importo},{status}\n")
    file_path.write_text("".join(lines), encoding="utf-8")
    return file_path


def test_engine_export_query_with_filter_groups(sample_dataset_path: Path, tmp_path: Path) -> None:
    """End-to-end verification: DuckDBEngine exports filtered rows correctly with filter_groups."""
    with DuckDBEngine() as engine:
        engine.connect_dataset(str(sample_dataset_path))

        group1 = FilterGroup(
            id="g1",
            rules=[FilterRule(column="Anno", operator=FilterOperator.EQUALS, value=2024)],
            logic=BooleanOperator.AND,
        )
        group2 = FilterGroup(
            id="g2",
            rules=[
                FilterRule(column="Regione", operator=FilterOperator.EQUALS, value="Lazio"),
            ],
            logic=BooleanOperator.AND,
        )
        spec = QuerySpec(
            filter_groups=[group1, group2],
            filter_group_logic=BooleanOperator.AND,
            limit=5,  # Export must export ALL matching rows, not just limit 5
            offset=0,
        )

        # Total matching rows in dataset: Anno=2024 (even indices: 0, 2, 4...) and Regione=Lazio (indices divisible by 3: 0, 3, 6...)
        # Indices divisible by 6: 0, 6, 12, 18, 24, 30, 36, 42, 48, 54, 60, 66, 72, 78, 84, 90, 96 -> exactly 17 rows
        count = engine.count_matching_rows(spec)
        assert count == 17

        export_out = tmp_path / "filtered_export.csv"
        exported_count = engine.export_query(spec, str(export_out), export_format="csv")
        assert exported_count == 17

        exported_content = export_out.read_text(encoding="utf-8").strip().splitlines()
        assert len(exported_content) == 18  # Header + 17 rows
        assert all("2024" in line and "Lazio" in line for line in exported_content[1:])


def test_engine_pagination_cache_with_filter_groups(sample_dataset_path: Path) -> None:
    """Verify DuckDBEngine pagination cache correctly preserves filter_groups on subsequent pages."""
    with DuckDBEngine() as engine:
        engine.connect_dataset(str(sample_dataset_path))

        group = FilterGroup(
            id="g1",
            rules=[FilterRule(column="Anno", operator=FilterOperator.EQUALS, value=2024)],
            logic=BooleanOperator.AND,
        )
        spec_page1 = QuerySpec(
            filter_groups=[group],
            order_by=[("Importo", True)],
            limit=10,
            offset=0,
        )
        res_page1 = engine.execute_query(spec_page1)
        assert res_page1.from_cache is False
        assert res_page1.total_matching_rows == 50
        assert res_page1.row_count == 10

        spec_page2 = QuerySpec(
            filter_groups=[group],
            order_by=[("Importo", True)],
            limit=10,
            offset=10,
        )
        res_page2 = engine.execute_query(spec_page2)
        assert res_page2.from_cache is True
        assert res_page2.total_matching_rows == 50
        assert res_page2.row_count == 10


def test_selective_materialization_avoids_temp_table_for_unfiltered_queries(sample_dataset_path: Path) -> None:
    """Verify that execute_query does NOT create _active_query_cache when there are no filters or ordering."""
    with DuckDBEngine() as engine:
        engine.connect_dataset(str(sample_dataset_path))

        spec = QuerySpec(limit=20, offset=0)
        res = engine.execute_query(spec)

        assert res.row_count == 20
        assert res.total_matching_rows == 100
        assert res.from_cache is False

        # Verify temp table was NOT created
        check_table = engine.conn.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_name = '_active_query_cache'"
        ).fetchone()
        assert check_table is None

        # Now execute a query with filters: temp table SHOULD be created
        spec_filtered = QuerySpec(
            filters=[FilterRule(column="Regione", operator=FilterOperator.EQUALS, value="Lazio")],
            limit=20,
            offset=0,
        )
        res_filtered = engine.execute_query(spec_filtered)
        assert res_filtered.row_count > 0

        check_table_filtered = engine.conn.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_name = '_active_query_cache'"
        ).fetchone()
        assert check_table_filtered is not None


def test_zero_copy_schema_inspection(tmp_path: Path) -> None:
    """Verify CsvAdapter and ParquetAdapter inspect schemas using PyArrow and fetchall without Pandas."""
    pq_file = tmp_path / "test.parquet"
    table = pa.table({
        "id": [1, 2, 3, 4, 5],
        "category": ["A", "B", "A", "B", "A"],
        "price": [10.5, 20.0, 30.2, 40.1, 50.0],
    })
    pq.write_table(table, str(pq_file))

    with DuckDBEngine() as engine:
        adapter = ParquetAdapter()
        schema = adapter.inspect_schema(str(pq_file), engine.conn)

        assert len(schema.columns) == 3
        col_id = schema.get_column("id")
        col_cat = schema.get_column("category")
        col_price = schema.get_column("price")

        assert col_id is not None and col_id.data_type == DataType.NUMERIC
        assert col_cat is not None and col_cat.data_type in (DataType.CATEGORICAL, DataType.TEXT)
        assert col_price is not None and col_price.data_type == DataType.NUMERIC
        assert col_price.has_native_numeric_type() is True


def test_engine_export_parquet_with_filter_groups(sample_dataset_path: Path, tmp_path: Path) -> None:
    """Verify DuckDBEngine exports filtered rows correctly to Parquet, readable by PyArrow."""
    with DuckDBEngine() as engine:
        engine.connect_dataset(str(sample_dataset_path))

        group1 = FilterGroup(
            id="g1",
            rules=[FilterRule(column="Anno", operator=FilterOperator.EQUALS, value=2024)],
            logic=BooleanOperator.AND,
        )
        group2 = FilterGroup(
            id="g2",
            rules=[FilterRule(column="Regione", operator=FilterOperator.EQUALS, value="Veneto")],
            logic=BooleanOperator.AND,
        )
        spec = QuerySpec(
            filter_groups=[group1, group2],
            filter_group_logic=BooleanOperator.AND,
            limit=2,  # Must be ignored in export
        )

        # Anno 2024 (even) and Veneto (i % 3 == 2) -> i in (2, 8, 14, 20, 26, 32, 38, 44, 50, 56, 62, 68, 74, 80, 86, 92, 98) -> 17 rows
        parquet_out = tmp_path / "filtered_export.parquet"
        exported_count = engine.export_query(spec, str(parquet_out), export_format="parquet")
        assert exported_count == 17

        # Read back with PyArrow to verify file contents
        table = pq.read_table(str(parquet_out))
        assert table.num_rows == 17
        assert "Anno" in table.column_names
        assert "Regione" in table.column_names
        assert all(val == 2024 for val in table.column("Anno").to_pylist())
        assert all(val == "Veneto" for val in table.column("Regione").to_pylist())


def test_engine_export_json_with_filter_groups(sample_dataset_path: Path, tmp_path: Path) -> None:
    """Verify DuckDBEngine exports filtered rows correctly to JSON array."""
    with DuckDBEngine() as engine:
        engine.connect_dataset(str(sample_dataset_path))

        group = FilterGroup(
            id="g1",
            rules=[
                FilterRule(column="Anno", operator=FilterOperator.EQUALS, value=2024),
                FilterRule(column="Status", operator=FilterOperator.EQUALS, value="Active"),
            ],
            logic=BooleanOperator.AND,
        )
        spec = QuerySpec(filter_groups=[group])

        json_out = tmp_path / "filtered_export.json"
        exported_count = engine.export_query(spec, str(json_out), export_format="json")
        assert exported_count == 25

        data = json.loads(json_out.read_text(encoding="utf-8"))
        assert len(data) == 25
        assert all(row["Anno"] == 2024 and row["Status"] == "Active" for row in data)


def test_engine_export_with_selected_columns_and_groups(sample_dataset_path: Path, tmp_path: Path) -> None:
    """Verify export preserves selected_columns projection when combined with filter_groups."""
    with DuckDBEngine() as engine:
        engine.connect_dataset(str(sample_dataset_path))

        group = FilterGroup(
            id="g1",
            rules=[FilterRule(column="Anno", operator=FilterOperator.EQUALS, value=2024)],
            logic=BooleanOperator.AND,
        )
        spec = QuerySpec(
            filter_groups=[group],
            selected_columns=["Regione", "Importo"],
        )

        csv_out = tmp_path / "projected_export.csv"
        engine.export_query(spec, str(csv_out), export_format="csv")

        header = csv_out.read_text(encoding="utf-8").splitlines()[0].split(",")
        assert header == ["Regione", "Importo"]


def test_engine_export_aggregated_with_filter_groups(sample_dataset_path: Path, tmp_path: Path) -> None:
    """Verify export of GROUP BY and Aggregations with filter_groups."""
    with DuckDBEngine() as engine:
        engine.connect_dataset(str(sample_dataset_path))

        group = FilterGroup(
            id="g1",
            rules=[FilterRule(column="Anno", operator=FilterOperator.EQUALS, value=2024)],
            logic=BooleanOperator.AND,
        )
        spec = QuerySpec(
            filter_groups=[group],
            group_by_columns=["Regione"],
            aggregations=[
                AggregationRule(column="Importo", func=AggregationFunc.SUM, alias="tot_importo"),
                AggregationRule(column="Importo", func=AggregationFunc.COUNT, alias="num_record"),
            ],
        )

        csv_out = tmp_path / "aggregated_export.csv"
        exported_count = engine.export_query(spec, str(csv_out), export_format="csv")
        assert exported_count == 3  # 3 regions: Lazio, Lombardia, Veneto

        lines = csv_out.read_text(encoding="utf-8").strip().splitlines()
        assert lines[0] == "Regione,tot_importo,num_record"
        assert len(lines) == 4  # header + 3 regions


def test_engine_export_with_or_filter_groups(sample_dataset_path: Path, tmp_path: Path) -> None:
    """Verify export correctly evaluates inter-group OR logic."""
    with DuckDBEngine() as engine:
        engine.connect_dataset(str(sample_dataset_path))

        group1 = FilterGroup(
            id="g1",
            rules=[FilterRule(column="Regione", operator=FilterOperator.EQUALS, value="Lazio")],
            logic=BooleanOperator.AND,
        )
        group2 = FilterGroup(
            id="g2",
            rules=[FilterRule(column="Regione", operator=FilterOperator.EQUALS, value="Veneto")],
            logic=BooleanOperator.AND,
        )
        spec = QuerySpec(
            filter_groups=[group1, group2],
            filter_group_logic=BooleanOperator.OR,
        )

        csv_out = tmp_path / "or_export.csv"
        exported_count = engine.export_query(spec, str(csv_out), export_format="csv")

        # In 100 rows, Lazio is ~34 rows, Veneto is ~33 rows, total ~67 rows
        assert exported_count == 67
        lines = csv_out.read_text(encoding="utf-8").strip().splitlines()[1:]
        assert all("Lazio" in line or "Veneto" in line for line in lines)
        assert not any("Lombardia" in line for line in lines)

