"""
Cross-platform native system file and folder picker.
Opens native OS dialogs (Finder on macOS, File Explorer on Windows, Zenity/Tkinter on Linux).
"""

import sys
import os
import subprocess
from pathlib import Path
from typing import Optional


def pick_system_folder(title: str = "Seleziona Cartella Dataset") -> Optional[str]:
    """Open native system folder selection dialog."""
    # 1. macOS Native AppleScript dialog
    if sys.platform == "darwin":
        try:
            script = f'POSIX path of (choose folder with prompt "{title}")'
            res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
            if res.returncode == 0 and res.stdout.strip():
                return res.stdout.strip().rstrip("/")
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


def pick_system_file(title: str = "Seleziona File Dataset") -> Optional[str]:
    """Open native system file selection dialog."""
    # 1. macOS Native AppleScript dialog
    if sys.platform == "darwin":
        try:
            script = f'POSIX path of (choose file with prompt "{title}")'
            res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
            if res.returncode == 0 and res.stdout.strip():
                return res.stdout.strip()
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
