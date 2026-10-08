"""
Tests for multi-process parallel XML-to-Parquet conversion (cores - 2).
"""

import os

import duckdb

from src.adapters.xml_adapter import XmlAdapter, _convert_single_xml_worker


def test_worker_calculation():
    """Verify max_workers defaults to cores - 2 (at least 1)."""
    cpu_count = os.cpu_count() or 4
    expected_workers = max(1, cpu_count - 2)
    assert expected_workers >= 1
    if cpu_count >= 4:
        assert expected_workers == cpu_count - 2


def test_convert_single_xml_worker_standalone(tmp_path):
    """Verify standalone worker can parse an XML file and output Parquet parts."""
    sample_file = "data/annihilation_test/2014_2015/OpenData_Aiuti_2014_01.xml"
    out_dir = tmp_path / "cache_worker"
    out_dir.mkdir()

    file_size, rows = _convert_single_xml_worker(
        fpath=sample_file,
        file_idx=0,
        output_dir_str=str(out_dir),
        target_tag="AIUTO",
        chunk_size=1000,
    )

    assert file_size == os.path.getsize(sample_file)
    assert rows == 574
    parquet_files = list(out_dir.glob("*.parquet"))
    assert len(parquet_files) >= 1

    # Verify DuckDB reads the parquet file
    con = duckdb.connect()
    cnt = con.execute(f"SELECT COUNT(*) FROM read_parquet('{out_dir!s}/*.parquet')").fetchone()[0]
    assert cnt == 574


def test_parallel_xml_conversion_multi_files(tmp_path):
    """Verify multi-process XML conversion across multiple files with progress reporting."""
    files = [
        "data/annihilation_test/2014_2015/OpenData_Aiuti_2014_01.xml",
        "data/annihilation_test/2014_2015/OpenData_Aiuti_2014_02.xml",
        "data/annihilation_test/2014_2015/OpenData_Aiuti_2014_03.xml",
    ]
    out_dir = tmp_path / "cache_parallel"
    xml_adapter = XmlAdapter()

    progress_events = []

    def on_progress(frac, bytes_done, rows_done):
        progress_events.append((frac, bytes_done, rows_done))

    # Test with max_workers=2
    xml_adapter.convert_to_parquet_streaming(
        files=files,
        output_dir=out_dir,
        chunk_size=5000,
        progress_callback=on_progress,
        max_workers=2,
    )

    # Check that parquet files were generated
    parquet_files = list(out_dir.glob("*.parquet"))
    assert len(parquet_files) == 3

    # Check total rows in DuckDB
    con = duckdb.connect()
    total_rows = con.execute(f"SELECT COUNT(*) FROM read_parquet('{out_dir!s}/*.parquet', union_by_name=true)").fetchone()[0]
    assert total_rows == (574 + 1 + 19)

    # Check progress callbacks fired
    assert len(progress_events) >= 3
    final_event = progress_events[-1]
    assert final_event[0] == 1.0  # 100% complete
    assert final_event[2] == total_rows


def test_sequential_fallback_single_worker(tmp_path):
    """Verify max_workers=1 runs sequentially and yields identical results."""
    files = [
        "data/annihilation_test/2014_2015/OpenData_Aiuti_2014_01.xml",
        "data/annihilation_test/2014_2015/OpenData_Aiuti_2014_02.xml",
    ]
    out_dir = tmp_path / "cache_seq"
    xml_adapter = XmlAdapter()

    xml_adapter.convert_to_parquet_streaming(
        files=files,
        output_dir=out_dir,
        max_workers=1,
    )

    con = duckdb.connect()
    total_rows = con.execute(f"SELECT COUNT(*) FROM read_parquet('{out_dir!s}/*.parquet', union_by_name=true)").fetchone()[0]
    assert total_rows == (574 + 1)
