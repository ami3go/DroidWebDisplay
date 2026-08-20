# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import sys

from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo,
    StringFileInfo,
    StringStruct,
    StringTable,
    VarFileInfo,
    VarStruct,
    VSVersionInfo,
)

sys.path.insert(0, SPECPATH)
import _dwd_common as common

if sys.platform != "win32":
    raise SystemExit("DroidWebDisplayWindowsOnedir.spec is a Windows-only target")

ROOT = common.repo_root(SPECPATH)
VERSION, numeric_version = common.read_version(ROOT)
ICON = common.windows_icon(ROOT, Path(globals().get("workpath") or (ROOT / "build")))

version_info = VSVersionInfo(
    ffi=FixedFileInfo(
        filevers=numeric_version,
        prodvers=numeric_version,
        mask=0x3F,
        flags=0x0,
        OS=0x40004,
        fileType=0x1,
        subtype=0x0,
        date=(0, 0),
    ),
    kids=[
        StringFileInfo([
            StringTable("040904B0", [
                StringStruct("CompanyName", "DroidWebDisplay contributors"),
                StringStruct("FileDescription", "DroidWebDisplay Android web display"),
                StringStruct("FileVersion", VERSION),
                StringStruct("InternalName", "DroidWebDisplay"),
                StringStruct("LegalCopyright", "Copyright DroidWebDisplay contributors"),
                StringStruct("OriginalFilename", "DroidWebDisplay.exe"),
                StringStruct("ProductName", "DroidWebDisplay"),
                StringStruct("ProductVersion", VERSION),
            ])
        ]),
        VarFileInfo([VarStruct("Translation", [1033, 1200])]),
    ],
)

a = Analysis(
    [str(ROOT.joinpath(*common.ENTRY_SCRIPT))],
    pathex=[str(ROOT), str(ROOT / "tools")],
    binaries=common.adb_binaries(common.adb_dir(), windows=True),
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
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ICON),
    version=version_info,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="DroidWebDisplayWindowsOnedir",
)
