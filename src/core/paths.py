"""
Filesystem path resolution and cache directory management for Grabber.
Cross-platform support for macOS, Windows, and Linux.
"""

import contextlib
import os
import shutil
import sys
from pathlib import Path


def get_app_cache_dir() -> Path:
    """Return OS-appropriate persistent cache directory for Grabber.

    Priority:
    1. GRABBER_CACHE_DIR environment variable if specified.
    2. Local .cache directory if it already exists in working directory.
    3. OS standard user cache folder:
       - macOS: ~/Library/Caches/Grabber
       - Windows: %LOCALAPPDATA%/Grabber/Cache
       - Linux: ~/.cache/grabber
    """
    override = os.getenv("GRABBER_CACHE_DIR")
    if override:
        path = Path(override).resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path

    local_cache = Path(".cache").resolve()
    if local_cache.exists() and (local_cache / "parquet_cache").exists():
        return local_cache

    if sys.platform == "darwin":
        path = Path.home() / "Library" / "Caches" / "Grabber"
    elif sys.platform == "win32":
        local_app_data = os.getenv("LOCALAPPDATA")
        path = (
            Path(local_app_data) / "Grabber" / "Cache"
            if local_app_data
            else Path.home() / "AppData" / "Local" / "Grabber" / "Cache"
        )
    else:
        xdg_cache = os.getenv("XDG_CACHE_HOME")
        path = (
            Path(xdg_cache) / "grabber"
            if xdg_cache
            else Path.home() / ".cache" / "grabber"
        )

    path.mkdir(parents=True, exist_ok=True)
    return path


def get_parquet_cache_dir() -> Path:
    """Return directory for cached converted Parquet files."""
    path = get_app_cache_dir() / "parquet_cache"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_spill_dir() -> Path:
    """Return directory for DuckDB out-of-core disk spillover."""
    path = get_app_cache_dir() / "duckdb_spill"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_cache_size_bytes() -> int:
    """Calculate total size in bytes of all cache and spill files."""
    cache_dir = get_app_cache_dir()
    if not cache_dir.exists():
        return 0
    total = 0
    for root, _, files in os.walk(cache_dir):
        for f in files:
            fp = os.path.join(root, f)
            with contextlib.suppress(OSError):
                total += os.path.getsize(fp)
    return total


def format_bytes(size_bytes: int) -> str:
    """Format bytes into human-readable string (KB, MB, GB)."""
    if size_bytes <= 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    size = float(size_bytes)
    while size >= 1024.0 and i < len(units) - 1:
        size /= 1024.0
        i += 1
    return f"{size:.1f} {units[i]}"


def clear_cache() -> int:
    """Remove all cached Parquet files and spillover temp files.

    Returns the number of bytes freed.
    """
    freed = get_cache_size_bytes()
    cache_dir = get_app_cache_dir()
    if cache_dir.exists():
        for item in cache_dir.iterdir():
            with contextlib.suppress(OSError):
                if item.is_dir():
                    shutil.rmtree(item, ignore_errors=True)
                else:
                    item.unlink(missing_ok=True)
    get_parquet_cache_dir().mkdir(parents=True, exist_ok=True)
    get_spill_dir().mkdir(parents=True, exist_ok=True)
    return freed
