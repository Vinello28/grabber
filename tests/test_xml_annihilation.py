"""
Benchmark and memory verification test on annihilation_test XML dataset.
"""

import os
import psutil
from src.adapters.xml_adapter import XmlAdapter
from src.engine.duckdb_engine import DuckDBEngine
from src.core.models import QuerySpec, FilterRule, FilterOperator


def test_xml_annihilation_streaming_memory():
    process = psutil.Process(os.getpid())
    sample_xml = "data/annihilation_test/2020/OpenData_Aiuti_2020_01.xml"

    adapter = XmlAdapter()
    tag = adapter.detect_record_tag(sample_xml)
    assert tag == "AIUTO"

    # Stream parse 10,000 records and check RSS memory
    initial_rss = process.memory_info().rss / (1024 * 1024)
    records_count = 0
    for record in adapter.iter_records(sample_xml, target_tag=tag, max_records=10000):
        records_count += 1
        assert "CAR" in record or "COR" in record

    final_rss = process.memory_info().rss / (1024 * 1024)
    rss_diff = final_rss - initial_rss

    print(f"Parsed {records_count} XML records. Initial RSS: {initial_rss:.1f}MB, Final RSS: {final_rss:.1f}MB (Diff: {rss_diff:.1f}MB)")
    assert records_count == 10000
    # Memory growth must be minimal (< 50MB) proving flat O(1) memory
    assert rss_diff < 50.0
