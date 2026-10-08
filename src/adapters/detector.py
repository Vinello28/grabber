"""
Dataset format and structure detector.
Identifies whether a path points to CSV, Parquet, XML, or a directory of files.
"""

from __future__ import annotations
import glob
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class DatasetDetector:
    """Detects format, file lists, and sizes of datasets."""

    SUPPORTED_EXTENSIONS = {
        ".csv": "csv",
        ".tsv": "csv",
        ".txt": "csv",
        ".parquet": "parquet",
        ".pq": "parquet",
        ".xml": "xml",
    }

    @classmethod
    def analyze_path(cls, path_str: str) -> Dict[str, any]:
        """
        Analyze path to return format, files list, total size, and directory status.
        Supports single files, directories, and glob patterns.
        """
        path_str = os.path.expanduser(path_str.strip())
        path = Path(path_str)

        files: List[str] = []
        fmt: Optional[str] = None

        if "*" in path_str or "?" in path_str:
            matched = sorted(glob.glob(path_str))
            files = [f for f in matched if os.path.isfile(f)]
        elif path.is_dir():
            # Check for direct files first, then recursive if needed
            for ext, f_type in cls.SUPPORTED_EXTENSIONS.items():
                direct_matches = sorted(glob.glob(os.path.join(path_str, f"*{ext}")))
                if direct_matches:
                    files = direct_matches
                    fmt = f_type
                    break
            
            # If no direct matches, check one level deeper or recursive
            if not files:
                for ext, f_type in cls.SUPPORTED_EXTENSIONS.items():
                    nested_matches = sorted(glob.glob(os.path.join(path_str, f"**/*{ext}"), recursive=True))
                    if nested_matches:
                        files = nested_matches
                        fmt = f_type
                        break
        elif path.is_file():
            files = [str(path)]
            ext = path.suffix.lower()
            fmt = cls.SUPPORTED_EXTENSIONS.get(ext)
        else:
            raise FileNotFoundError(f"Path does not exist: {path_str}")

        if not files:
            raise ValueError(f"No supported data files (.csv, .parquet, .xml) found in: {path_str}")

        if not fmt:
            first_ext = Path(files[0]).suffix.lower()
            fmt = cls.SUPPORTED_EXTENSIONS.get(first_ext, "unknown")

        total_size = sum(os.path.getsize(f) for f in files)

        return {
            "source_path": path_str,
            "format": fmt,
            "file_count": len(files),
            "files": files,
            "total_size_bytes": total_size,
            "is_directory": path.is_dir(),
        }
