# -*- mode: python ; coding: utf-8 -*-

import os
import re

# Get version from the main script dynamically
version = "2025.01"  # Default fallback
try:
    with open('kmall_to_pkl_converter.py', 'r', encoding='utf-8') as f:
        content = f.read()
        match = re.search(r"__version__\s*=\s*['\"]([^'\"]+)['\"]", content)
        if match:
            version = match.group(1)
except Exception:
    pass  # Use default version if reading fails

a = Analysis(
    ['kmall_to_pkl_converter.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('libs', 'libs'),  # Include the libs folder
    ],
    hiddenimports=[
        'libs.swath_fun',
        'libs.kmall',
        'libs.parseEM',
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name=f'KMALL_to_SwathPKL_V{version}',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # No terminal window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join('media', 'CCOM.ico') if os.path.exists(os.path.join('media', 'CCOM.ico')) else None,
)
