"""
Dataset format and structure detector.
Identifies whether a path points to CSV, Parquet, XML, or a directory of files.
"""

from __future__ import annotations

import glob
import os
from pathlib import Path
from typing import Any, ClassVar


class DatasetDetector:
    """Detects format, file lists, and sizes of datasets with single-pass scanning and mtime caching."""

    SUPPORTED_EXTENSIONS: ClassVar[dict[str, str]] = {
        ".csv": "csv",
        ".tsv": "csv",
        ".txt": "csv",
        ".parquet": "parquet",
        ".pq": "parquet",
        ".xml": "xml",
    }

    _cache: ClassVar[dict[str, tuple[float, dict[str, Any]]]] = {}

    @classmethod
    def analyze_path(cls, path_str: str) -> dict[str, Any]:
        """Analyze path to return format, files list, total size, and directory status.

        Supports single files, directories, and glob patterns with caching.
        """
        path_str = os.path.expanduser(path_str.strip().strip("'\""))
        path = Path(path_str)

        # Fast mtime check for directory/file cache
        try:
            mtime = path.stat().st_mtime if path.exists() else 0.0
        except OSError:
            mtime = 0.0

        resolved_key = str(path.resolve()) if path.exists() else path_str
        if resolved_key in cls._cache:
            cached_mtime, cached_res = cls._cache[resolved_key]
            if cached_mtime == mtime and mtime > 0.0:
                # Return copy with current path_str
                res_copy = dict(cached_res)
                res_copy["source_path"] = path_str
                return res_copy

        files: list[str] = []
        fmt: str | None = None
        total_size = 0

        if "*" in path_str or "?" in path_str:
            matched = sorted(glob.glob(path_str))
            files = [f for f in matched if os.path.isfile(f) and not os.path.basename(f).startswith((".", "~$"))]
            if files:
                ext = Path(files[0]).suffix.lower()
                fmt = cls.SUPPORTED_EXTENSIONS.get(ext, "unknown")
                total_size = sum(os.path.getsize(f) for f in files)
        elif path.is_file():
            if not os.path.basename(path_str).startswith((".", "~$")):
                files = [str(path)]
                ext = path.suffix.lower()
                fmt = cls.SUPPORTED_EXTENSIONS.get(ext)
                total_size = path.stat().st_size
        elif path.is_dir():
            # 1. Single-pass over direct children first
            format_buckets: dict[str, list[tuple[str, int]]] = {}
            has_subdirs = False

            try:
                with os.scandir(path) as it:
                    for entry in it:
                        name = entry.name
                        if name.startswith((".", "~$")):
                            continue
                        if entry.is_file():
                            ext = os.path.splitext(name)[1].lower()
                            f_type = cls.SUPPORTED_EXTENSIONS.get(ext)
                            if f_type:
                                format_buckets.setdefault(f_type, []).append((entry.path, entry.stat().st_size))
                        elif entry.is_dir():
                            has_subdirs = True
            except OSError as err:
                raise FileNotFoundError(f"Errore lettura cartella {path_str}: {err}") from err

            # Check direct matches by format priority
            for _, f_type in cls.SUPPORTED_EXTENSIONS.items():
                if f_type in format_buckets:
                    items = sorted(format_buckets[f_type], key=lambda x: x[0])
                    files = [x[0] for x in items]
                    total_size = sum(x[1] for x in items)
                    fmt = f_type
                    break

            # 2. If no direct files and directory has subdirs, do a single-pass recursive walk
            if not files and has_subdirs:
                recursive_buckets: dict[str, list[tuple[str, int]]] = {}
                for root, _, dir_files in os.walk(path):
                    for fn in dir_files:
                        if fn.startswith((".", "~$")):
                            continue
                        ext = os.path.splitext(fn)[1].lower()
                        f_type = cls.SUPPORTED_EXTENSIONS.get(ext)
                        if f_type:
                            fp = os.path.join(root, fn)
                            try:
                                sz = os.path.getsize(fp)
                            except OSError:
                                sz = 0
                            recursive_buckets.setdefault(f_type, []).append((fp, sz))

                for _, f_type in cls.SUPPORTED_EXTENSIONS.items():
                    if f_type in recursive_buckets:
                        items = sorted(recursive_buckets[f_type], key=lambda x: x[0])
                        files = [x[0] for x in items]
                        total_size = sum(x[1] for x in items)
                        fmt = f_type
                        break
        else:
            raise FileNotFoundError(f"Path does not exist: {path_str}")

        if not files:
            raise ValueError(f"No supported data files (.csv, .parquet, .xml) found in: {path_str}")

        if not fmt:
            first_ext = Path(files[0]).suffix.lower()
            fmt = cls.SUPPORTED_EXTENSIONS.get(first_ext, "unknown")

        result = {
            "source_path": path_str,
            "format": fmt,
            "file_count": len(files),
            "files": files,
            "total_size_bytes": total_size,
            "is_directory": path.is_dir(),
        }

        if mtime > 0.0:
            cls._cache[resolved_key] = (mtime, result)

        return result

