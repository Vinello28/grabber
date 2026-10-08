"""
Cross-platform native system file and folder picker.
Opens native OS dialogs (Finder on macOS, File Explorer on Windows, Zenity/Tkinter on Linux).
"""

import subprocess
import sys
from pathlib import Path


def pick_system_folder(title: str = "Seleziona Cartella Dataset") -> str | None:
    """Open native system folder selection dialog."""
    # 1. macOS Native AppleScript dialog
    if sys.platform == "darwin":
        try:
            escaped_title = title.replace("\\", "\\\\").replace('"', '\\"')
            script = f'POSIX path of (choose folder with prompt "{escaped_title}")'
            res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, check=False)
            if res.returncode == 0 and res.stdout.strip():
                return res.stdout.strip().rstrip("/")
            # If user explicitly canceled in AppleScript, don't fallback to Tkinter
            if "canceled" in res.stderr.lower() or "cancelled" in res.stderr.lower() or "-128" in res.stderr:
                return None
        except Exception:
            pass

    # 2. Windows / Linux / macOS Fallback with Tkinter
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        selected = filedialog.askdirectory(title=title)
        root.destroy()
        if selected:
            return str(Path(selected).resolve())
    except Exception:
        pass

    return None


def pick_system_file(title: str = "Seleziona File Dataset") -> str | None:
    """Open native system file selection dialog."""
    # 1. macOS Native AppleScript dialog
    if sys.platform == "darwin":
        try:
            escaped_title = title.replace("\\", "\\\\").replace('"', '\\"')
            script = f'POSIX path of (choose file with prompt "{escaped_title}")'
            res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, check=False)
            if res.returncode == 0 and res.stdout.strip():
                return res.stdout.strip()
            # If user explicitly canceled in AppleScript, don't fallback to Tkinter
            if "canceled" in res.stderr.lower() or "cancelled" in res.stderr.lower() or "-128" in res.stderr:
                return None
        except Exception:
            pass

    # 2. Windows / Linux / macOS Fallback with Tkinter
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        filetypes = [
            ("Dataset Files (*.csv, *.parquet, *.xml)", "*.csv *.tsv *.txt *.parquet *.pq *.xml"),
            ("Tutti i file", "*.*"),
        ]
        selected = filedialog.askopenfilename(title=title, filetypes=filetypes)
        root.destroy()
        if selected:
            return str(Path(selected).resolve())
    except Exception:
        pass

    return None
