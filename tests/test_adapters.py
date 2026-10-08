"""
Unit tests for data adapters (CSV, Parquet, XML, Detector).
"""

import os
from src.adapters.detector import DatasetDetector
from src.adapters.csv_adapter import CsvAdapter
from src.adapters.xml_adapter import XmlAdapter


def test_detector_csv():
    analysis = DatasetDetector.analyze_path("data/test1")
    assert analysis["format"] == "csv"
    assert analysis["file_count"] == 12
    assert analysis["total_size_bytes"] > 10 * (1024 ** 3)  # > 10 GB


def test_detector_xml():
    analysis = DatasetDetector.analyze_path("data/annihilation_test")
    assert analysis["format"] == "xml"
    assert analysis["file_count"] > 10


def test_csv_adapter_sniff_delimiter():
    adapter = CsvAdapter()
    sample_file = "data/test1/reclassified_multiclass_aiuti_2014.csv"
    delim = adapter.sniff_delimiter(sample_file)
    assert delim == ","


def test_xml_adapter_record_detection():
    adapter = XmlAdapter()
    sample_file = "data/annihilation_test/2014_2015/OpenData_Aiuti_2014_01.xml"
    tag = adapter.detect_record_tag(sample_file)
    assert tag == "AIUTO"

    # Test reading a few streaming records
    records = list(adapter.iter_records(sample_file, max_records=5))
    assert len(records) == 5
    assert "CAR" in records[0]
    assert "DENOMINAZIONE_BENEFICIARIO" in records[0]
    assert records[0]["FILE_SOURCE"] == "OpenData_Aiuti_2014_01.xml"
