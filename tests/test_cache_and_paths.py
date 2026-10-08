"""
Unit tests for OS cache management, paths resolution, and cache clearing.
"""

from pathlib import Path

from src.core.paths import (
    clear_cache,
    format_bytes,
    get_app_cache_dir,
    get_cache_size_bytes,
    get_parquet_cache_dir,
    get_spill_dir,
)


def test_format_bytes():
    assert format_bytes(0) == "0 B"
    assert format_bytes(500) == "500.0 B"
    assert format_bytes(1024) == "1.0 KB"
    assert format_bytes(1024 * 1024) == "1.0 MB"
    assert format_bytes(1024 * 1024 * 1024) == "1.0 GB"


def test_paths_override_with_env(monkeypatch, tmp_path: Path):
    custom_dir = tmp_path / "custom_cache"
    monkeypatch.setenv("GRABBER_CACHE_DIR", str(custom_dir))

    cache_dir = get_app_cache_dir()
    assert cache_dir == custom_dir.resolve()
    assert cache_dir.exists()

    pq_dir = get_parquet_cache_dir()
    assert pq_dir == custom_dir / "parquet_cache"
    assert pq_dir.exists()

    spill_dir = get_spill_dir()
    assert spill_dir == custom_dir / "duckdb_spill"
    assert spill_dir.exists()


def test_clear_cache(monkeypatch, tmp_path: Path):
    custom_dir = tmp_path / "custom_cache_clear"
    monkeypatch.setenv("GRABBER_CACHE_DIR", str(custom_dir))

    pq_dir = get_parquet_cache_dir()
    dummy_file = pq_dir / "sample.parquet"
    dummy_file.write_bytes(b"x" * 2048)

    spill_dir = get_spill_dir()
    dummy_spill = spill_dir / "spill.tmp"
    dummy_spill.write_bytes(b"y" * 1024)

    size = get_cache_size_bytes()
    assert size == 3072

    freed = clear_cache()
    assert freed == 3072
    assert get_cache_size_bytes() == 0
    assert pq_dir.exists()
    assert spill_dir.exists()
