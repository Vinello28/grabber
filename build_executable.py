"""
Automated Build Script for Grabber Desktop Executable.
Generates icons if missing, executes PyInstaller, and packages output.
"""

import os
import sys
import subprocess
from pathlib import Path


def main():
    root_dir = Path(__file__).resolve().parent
    print("=" * 60)
    print("🔨 Compilazione Eseguibile Grabber (PyInstaller)")
    print("=" * 60)

    # 1. Generate icons
    icon_script = root_dir / "scripts" / "generate_icons.py"
    if icon_script.exists():
        print("Controllo/Generazione icone applicazione...")
        subprocess.run([sys.executable, str(icon_script)], check=True)

    # 2. Run PyInstaller
    spec_file = root_dir / "grabber.spec"
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        str(spec_file),
    ]

    print(f"Esecuzione comando: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)

    dist_dir = root_dir / "dist"
    print("=" * 60)
    print("✅ Build completata con successo!")
    print(f"I file eseguibili si trovano in: {dist_dir}")
    if sys.platform == "darwin":
        print(f"Applicazione macOS: {dist_dir / 'Grabber.app'}")
    elif sys.platform == "win32":
        print(f"Eseguibile Windows: {dist_dir / 'Grabber' / 'Grabber.exe'}")
    else:
        print(f"Eseguibile Linux: {dist_dir / 'Grabber' / 'Grabber'}")
    print("=" * 60)


if __name__ == "__main__":
    main()
