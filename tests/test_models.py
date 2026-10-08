"""
Unit tests for core models and specifications.
"""

from src.core.models import (
    ColumnMeta,
    DatasetSchema,
    DataType,
    QuerySpec,
)


def test_column_meta():
    col = ColumnMeta(name="IMPORTO", data_type=DataType.NUMERIC, native_type="DOUBLE")
    assert col.is_numeric() is True
    assert col.is_text() is False

    col_text = ColumnMeta(name="CODICE_FISCALE", data_type=DataType.TEXT)
    assert col_text.is_numeric() is False
    assert col_text.is_text() is True


def test_dataset_schema():
    cols = [
        ColumnMeta("ID", DataType.NUMERIC),
        ColumnMeta("NOME", DataType.TEXT),
    ]
    schema = DatasetSchema(
        source_path="/path/test",
        source_format="csv",
        columns=cols,
        row_count_estimate=1000,
    )
    assert schema.column_names == ["ID", "NOME"]
    assert schema.get_column("ID") is not None
    assert schema.get_column("NON_ESISTE") is None


def test_query_spec_defaults():
    spec = QuerySpec()
    assert spec.filters == []
    assert spec.global_search is None
    assert spec.limit is None
