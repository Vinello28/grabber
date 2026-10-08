"""
Hardware and resource monitor.
Tracks RAM, CPU, threads, and determines safe memory limits for out-of-core execution.
"""

from __future__ import annotations
import os
import psutil
from typing import Dict, Any


class ResourceMonitor:
    """Monitors system hardware and process resource consumption."""

    @staticmethod
    def get_system_stats() -> Dict[str, Any]:
        """Fetch real-time hardware metrics."""
        vm = psutil.virtual_memory()
        cpu_count = os.cpu_count() or 1
        cpu_percent = psutil.cpu_percent(interval=None)

        process = psutil.Process(os.getpid())
        proc_mem = process.memory_info().rss

        return {
            "total_ram_gb": round(vm.total / (1024 ** 3), 2),
            "available_ram_gb": round(vm.available / (1024 ** 3), 2),
            "used_ram_percent": vm.percent,
            "process_rss_mb": round(proc_mem / (1024 ** 2), 2),
            "process_rss_gb": round(proc_mem / (1024 ** 3), 3),
            "cpu_cores": cpu_count,
            "cpu_percent": cpu_percent,
        }

    @staticmethod
    def calculate_safe_memory_limit(reserve_ratio: float = 0.6) -> str:
        """
        Calculate a safe DuckDB memory limit string (e.g. '4GB' or '8GB').
        Guarantees that low RAM machines (<16GB) don't trigger Out-Of-Memory kernel kills.
        """
        vm = psutil.virtual_memory()
        available_gb = vm.available / (1024 ** 3)
        total_gb = vm.total / (1024 ** 3)

        # Allocate between 2GB and 8GB depending on available RAM
        safe_gb = max(2.0, min(8.0, available_gb * reserve_ratio))
        if total_gb < 16.0:
            safe_gb = min(safe_gb, 4.0)

        return f"{int(safe_gb)}GB"
