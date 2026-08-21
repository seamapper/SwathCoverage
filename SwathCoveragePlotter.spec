# -*- mode: python ; coding: utf-8 -*-

import os
import re

# Get version from the main script dynamically (script is in cwd when building)
version = "2026.01"  # Default fallback
_script_path = os.path.join(os.getcwd(), 'swath_coverage_plotter.py')
try:
    with open(_script_path, 'r', encoding='utf-8') as f:
        content = f.read()
        for line in content.split('\n'):
            stripped = line.strip()
            if stripped.startswith('#'):
                continue
            match = re.search(r"__version__\s*=\s*['\"]([^'\"]+)['\"]", line)
            if match:
                version = match.group(1)
                break
except Exception:
    pass  # Use default version if reading fails

# Bundle mbtoolkit GSF reader when present (optional; enables .gsf coverage import in the exe)
_datas = [
    ('libs', 'libs'),  # Include the libs folder
    ('media', 'media'),  # Include the media folder
]
_mbtoolkit_bundled = False
for _mbtoolkit_dir in ('mbtoolkit_gsf', 'mbtoolkit'):
    _reader_marker = os.path.join(_mbtoolkit_dir, 'readers', 'base', 'pygsf.py')
    if os.path.isfile(_reader_marker):
        _datas.append((_mbtoolkit_dir, _mbtoolkit_dir))
        _mbtoolkit_bundled = True
        print(f'Including {_mbtoolkit_dir} for GSF support')
        break
if not _mbtoolkit_bundled:
    print('NOTE: mbtoolkit not found — GSF (.gsf) support will be disabled in the executable')
    print('      Download from https://github.com/oceanmapping/mbtoolkit and place as')
    print('      mbtoolkit/ or mbtoolkit_gsf/ next to this spec before building.')

a = Analysis(
    ['swath_coverage_plotter.py'],
    pathex=[],
    binaries=[],
    datas=_datas,
    hiddenimports=[
        'libs.swath_fun',
        'libs.swath_coverage_lib',
        'libs.kmall',
        'libs.parseEM',
        'libs.file_fun',
        'libs.gui_widgets',
        'libs.parse_guard',
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
    name=f'Swath_Coverage_Plotter_v{version}',
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
    icon=os.path.join('media', 'mac.ico') if os.path.exists(os.path.join('media', 'mac.ico')) else None,
)
