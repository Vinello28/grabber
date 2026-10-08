# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller Specification for Grabber Desktop Executable.
Cross-platform packaging for Windows (.exe), macOS (.app), and Linux.
"""

import sys
import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, copy_metadata, collect_submodules

block_cipher = None

root_dir = os.path.abspath(SPECPATH)

# 1. Collect Streamlit & Dependencies data files and metadata
datas = [
    (os.path.join(root_dir, 'src'), 'src'),
    (os.path.join(root_dir, 'assets'), 'assets'),
]
datas += collect_data_files('streamlit')
datas += copy_metadata('streamlit')

# 2. Hidden imports
hiddenimports = [
    'duckdb',
    'pyarrow',
    'pyarrow.parquet',
    'lxml',
    'lxml.etree',
    'streamlit',
    'streamlit.web.bootstrap',
    'pandas',
    'altair',
    'psutil',
]
hiddenimports += collect_submodules('streamlit')
hiddenimports += collect_submodules('src')

# 3. Determine icon based on OS
if sys.platform == 'win32':
    icon_file = os.path.join(root_dir, 'assets', 'icon.ico')
elif sys.platform == 'darwin':
    icon_file = os.path.join(root_dir, 'assets', 'icon.icns')
else:
    icon_file = os.path.join(root_dir, 'assets', 'icon.png')

a = Analysis(
    [os.path.join(root_dir, 'desktop_entrypoint.py')],
    pathex=[root_dir],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'scipy', 'torch', 'tensorflow'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Grabber',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # No terminal window on double-click
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_file if os.path.exists(icon_file) else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Grabber',
)

# On macOS, generate native .app bundle
if sys.platform == 'darwin':
    app = BUNDLE(
        coll,
        name='Grabber.app',
        icon=icon_file if os.path.exists(icon_file) else None,
        bundle_identifier='com.grabber.bigdata',
        info_plist={
            'CFBundleName': 'Grabber',
            'CFBundleDisplayName': 'Grabber',
            'CFBundleGetInfoString': "Grabber Big Data Analytical Engine",
            'CFBundleIdentifier': "com.grabber.bigdata",
            'CFBundleVersion': "1.0.0",
            'CFBundleShortVersionString': "1.0.0",
            'NSHighResolutionCapable': True,
        },
    )
