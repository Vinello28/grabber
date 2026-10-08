"""
Automated Build Script for Grabber Desktop Executable.
Generates icons if missing, executes PyInstaller, and packages output.
"""

import contextlib
import os
import subprocess
import sys
from pathlib import Path


def sync_version_from_git_or_env(root_dir: Path):
    """Sync src/core/version.py from Git tag or environment variable if present."""
    version = None
    env_ref = os.environ.get("GITHUB_REF_NAME") or os.environ.get("GITHUB_REF", "")
    if env_ref:
        version = env_ref.split("/")[-1].lstrip("v")

    if not version:
        try:
            res = subprocess.run(
                ["git", "describe", "--tags", "--exact-match"],
                cwd=root_dir,
                capture_output=True,
                text=True,
                check=False,
            )
            if res.returncode == 0 and res.stdout.strip():
                version = res.stdout.strip().lstrip("v")
        except Exception:
            pass

    if version:
        version_file = root_dir / "src" / "core" / "version.py"
        if version_file.exists():
            content = version_file.read_text(encoding="utf-8")
            lines = []
            for line in content.splitlines():
                if line.startswith("__version__ ="):
                    lines.append(f'__version__ = "{version}"')
                else:
                    lines.append(line)
            version_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
            print(f"[VERSION] Versione sincronizzata da Git/CI: {version}")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        with contextlib.suppress(Exception):
            sys.stdout.reconfigure(encoding="utf-8")

    root_dir = Path(__file__).resolve().parent
    print("=" * 60)
    print("[BUILD] Compilazione Eseguibile Grabber (PyInstaller)")
    print("=" * 60)

    # Sync version if building in CI or tagged commit
    sync_version_from_git_or_env(root_dir)

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
    print("[OK] Build completata con successo!")
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
