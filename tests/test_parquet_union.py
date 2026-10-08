"""
Tests for Parquet glob reading and export with heterogeneous schemas (union_by_name=True).
Verifies that schema mismatches across globbed parquet chunks (e.g. missing optional columns)
do not fail queries or exports.
"""

import os
from pathlib import Path
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from src.adapters.parquet_adapter import ParquetAdapter
from src.adapters.xml_adapter import XmlAdapter
from src.engine.duckdb_engine import DuckDBEngine
from src.core.models import QuerySpec


def test_parquet_adapter_union_by_name(tmp_path: Path):
    """Verify ParquetAdapter build_sql_source includes union_by_name=true."""
    adapter = ParquetAdapter()
    sql = adapter.build_sql_source(str(tmp_path / "*.parquet"))
    assert "union_by_name=true" in sql.lower()

    sql_list = adapter.build_sql_source([str(tmp_path / "1.parquet"), str(tmp_path / "2.parquet")])
    assert "union_by_name=true" in sql_list.lower()


def test_xml_adapter_cache_path_normalization():
    """Ensure relative and absolute paths resolve to the exact same cache directory."""
    adapter = XmlAdapter()
    rel_path = "data/annihilation_test/2014_2015"
    abs_path = str(Path(rel_path).resolve())

    cache_rel = adapter.get_cache_path(rel_path)
    cache_abs = adapter.get_cache_path(abs_path)

    assert cache_rel == cache_abs, f"Cache paths differed: {cache_rel} != {cache_abs}"


def test_heterogeneous_parquet_chunks_query_and_export(tmp_path: Path):
    """
    Simulates the exact crash condition:
    - part_0000.parquet has ['ID', 'NAME', 'ATTO_CONCESSIONE']
    - part_0001.parquet has ['ID', 'NAME', 'OTHER_FIELD'] (missing 'ATTO_CONCESSIONE')
    Without union_by_name=True, DuckDB raises:
        'schema mismatch in glob: column ATTO_CONCESSIONE could not be found'
    """
    df1 = pd.DataFrame({
        "ID": [1, 2],
        "NAME": ["Alpha", "Beta"],
        "ATTO_CONCESSIONE": ["ATTO_001", "ATTO_002"],
    })
    df2 = pd.DataFrame({
        "ID": [3, 4],
        "NAME": ["Gamma", "Delta"],
        "OTHER_FIELD": [100.5, 200.75],
    })

    file1 = tmp_path / "part_0000.parquet"
    file2 = tmp_path / "part_0001.parquet"

    pq.write_table(pa.Table.from_pandas(df1), file1)
    pq.write_table(pa.Table.from_pandas(df2), file2)

    engine = DuckDBEngine()
    schema = engine.connect_dataset(str(tmp_path / "*.parquet"))

    assert "ATTO_CONCESSIONE" in schema.column_names
    assert "OTHER_FIELD" in schema.column_names

    # 1. Execute normal query
    spec = QuerySpec()
    res = engine.execute_query(spec)
    assert res.total_matching_rows == 4

    # 2. Export to CSV
    csv_file = tmp_path / "export.csv"
    exported_csv = engine.export_query(spec, str(csv_file), export_format="csv")
    assert exported_csv == 4
    assert csv_file.exists()
    content = csv_file.read_text()
    assert "ATTO_CONCESSIONE" in content
    assert "OTHER_FIELD" in content

    # 3. Export to Parquet
    pq_out = tmp_path / "export.parquet"
    exported_pq = engine.export_query(spec, str(pq_out), export_format="parquet")
    assert exported_pq == 4
    assert pq_out.exists()


def test_cached_xml_export_with_atto_concessione(tmp_path: Path):
    """Test directly against the cached XML dataset with 22 files and differing schemas."""
    cache_dir = Path(".cache/parquet_cache/xml_be9386a025b6")
    if not cache_dir.exists():
        pytest.skip("Cache directory xml_be9386a025b6 does not exist")

    engine = DuckDBEngine()
    schema = engine.connect_dataset("data/annihilation_test/2014_2015")

    assert "ATTO_CONCESSIONE" in schema.column_names

    spec = QuerySpec()
    export_out = tmp_path / "export_test_2014.csv"
    count = engine.export_query(spec, str(export_out), export_format="csv")

    assert count > 0
    assert export_out.exists()
    assert os.path.getsize(export_out) > 1000
