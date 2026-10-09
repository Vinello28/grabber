#!/usr/bin/env python3
"""
Grabber Application Launcher.
Cross-platform launcher for macOS, Windows, and Linux.
Automatically starts the Streamlit GUI in the local browser.

Copyright (c) 2026 Gabriele Vianello <vianello.tech@gmail.com>.
Licensed under Grabber Restrictive Non-Commercial License (RNC-1.0).
"""

import contextlib
import multiprocessing
import subprocess
import sys
from pathlib import Path


def build_streamlit_cmd(sys_executable: str, app_path: Path) -> list[str]:
    """Construct command arguments to launch Streamlit safely on 127.0.0.1 loopback."""
    return [
        sys_executable,
        "-m",
        "streamlit",
        "run",
        str(app_path),
        "--server.address=127.0.0.1",
        "--browser.serverAddress=127.0.0.1",
        "--server.headless=false",
        "--server.enableCORS=false",
        "--server.enableXsrfProtection=false",
        "--browser.gatherUsageStats=false",
    ]


def main():
    if hasattr(sys.stdout, "reconfigure"):
        with contextlib.suppress(Exception):
            sys.stdout.reconfigure(encoding="utf-8")

    root_dir = Path(__file__).resolve().parent
    app_path = root_dir / "src" / "ui" / "app.py"

    print("=" * 60)
    print("GRABBER - Big Data Analytical Engine")
    print("Copyright (c) 2026 Gabriele Vianello")
    print("Grabber Restrictive Non-Commercial License (RNC-1.0)")
    print("=" * 60)
    print(f"Directory di lavoro: {root_dir}")
    print(f"Applicazione: {app_path}")
    print("Avvio interfaccia grafica Streamlit...")
    print("=" * 60)

    # Launch Streamlit
    cmd = build_streamlit_cmd(sys.executable, app_path)

    try:
        subprocess.run(cmd, check=True)
    except KeyboardInterrupt:
        print("\nApplicazione terminata dall'utente.")
    except Exception as e:
        print(f"\nErrore durante l'esecuzione: {e}")
        sys.exit(1)


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
