# -*- mode: python ; coding: utf-8 -*-

import os
import re

# Get version from the main script dynamically
version = "2025.11"  # Default fallback
try:
    with open('swath_coverage_plotter.py', 'r', encoding='utf-8') as f:
        content = f.read()
        # Match __version__ that is not commented out (not preceded by #)
        # Look for lines that don't start with # or have # after the version assignment
        for line in content.split('\n'):
            # Skip commented lines
            stripped = line.strip()
            if stripped.startswith('#'):
                continue
            # Match uncommented __version__ lines
            match = re.search(r"__version__\s*=\s*['\"]([^'\"]+)['\"]", line)
            if match:
                version = match.group(1)
                break
except Exception:
    pass  # Use default version if reading fails

a = Analysis(
    ['swath_coverage_plotter.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('libs', 'libs'),  # Include the libs folder
        ('media', 'media'),  # Include the media folder
    ],
    hiddenimports=[
        'libs.swath_fun',
        'libs.swath_coverage_lib',
        'libs.kmall',
        'libs.parseEM',
        'libs.file_fun',
        'libs.gui_widgets',
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
    name=f'Swath Coverage Plotter V{version}',
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

