"""
Desktop Standalone Entrypoint for Grabber.
Directly bootstraps Streamlit in-process and opens the local browser.
Designed for PyInstaller standalone executables (.exe, .app, Linux binary).
"""

import os
import sys
from pathlib import Path
import webbrowser
import streamlit.web.bootstrap as bootstrap


def get_base_dir() -> Path:
    """Return base directory whether running from source or PyInstaller bundle."""
    if getattr(sys, "frozen", False):
        # Running as PyInstaller frozen executable
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent


def main():
    base_dir = get_base_dir()
    app_path = base_dir / "src" / "ui" / "app.py"

    # Ensure src is in sys.path
    if str(base_dir) not in sys.path:
        sys.path.insert(0, str(base_dir))

    flag_options = {
        "server.headless": False,
        "browser.gatherUsageStats": False,
        "server.address": "localhost",
        "global.developmentMode": False,
    }

    # Start Streamlit in-process
    bootstrap.run(
        str(app_path),
        is_hello=False,
        args=[],
        flag_options=flag_options,
    )


if __name__ == "__main__":
    main()
