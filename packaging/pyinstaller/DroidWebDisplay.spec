# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import sys

sys.path.insert(0, SPECPATH)
import _dwd_common as common

if sys.platform == "win32":
    # Windows has dedicated specs that attach the icon and the VS version
    # resource. This one produces neither, so falling back to it here builds
    # exactly the binary ci.yml's PE metadata check exists to reject.
    raise SystemExit(
        "Use packaging/pyinstaller/DroidWebDisplayWindows.spec or "
        "DroidWebDisplayWindowsOnedir.spec on Windows"
    )

ROOT = common.repo_root(SPECPATH)

a = Analysis(
    [str(ROOT.joinpath(*common.ENTRY_SCRIPT))],
    pathex=[str(ROOT), str(ROOT / "tools")],
    binaries=common.adb_binaries(common.adb_dir(), windows=False),
    datas=common.bundle_datas(ROOT),
    hiddenimports=common.hidden_imports(),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

# upx is intentionally disabled, matching both Windows specs. It was never
# installed on the Linux runner, so upx=True silently did nothing -- and would
# have activated unreviewed the moment upx appeared, which on Qt binaries is a
# known source of corrupt executables and antivirus false positives.
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="DroidWebDisplay",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="DroidWebDisplay",
)
