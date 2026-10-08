#!/usr/bin/env python3
"""
Grabber Application Launcher.
Cross-platform launcher for macOS, Windows, and Linux.
Automatically starts the Streamlit GUI in the local browser.
"""

import os
import sys
import subprocess
from pathlib import Path


def main():
    root_dir = Path(__file__).resolve().parent
    app_path = root_dir / "src" / "ui" / "app.py"

    print("=" * 60)
    print("⚡ GRABBER - Big Data Analytical Engine")
    print("   Cross-Platform Out-of-Core Data Query & Export GUI")
    print("=" * 60)
    print(f"Directory di lavoro: {root_dir}")
    print(f"Applicazione: {app_path}")
    print("Avvio interfaccia grafica Streamlit...")
    print("=" * 60)

    # Launch Streamlit
    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(app_path),
        "--server.headless=false",
        "--browser.gatherUsageStats=false",
    ]

    try:
        subprocess.run(cmd, check=True)
    except KeyboardInterrupt:
        print("\nApplicazione terminata dall'utente.")
    except Exception as e:
        print(f"\nErrore durante l'esecuzione: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
