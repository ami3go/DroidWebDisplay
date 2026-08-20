# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import base64
import os
import sys

from PyInstaller.utils.hooks import collect_submodules
from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo,
    StringFileInfo,
    StringStruct,
    StringTable,
    VarFileInfo,
    VarStruct,
    VSVersionInfo,
)

if sys.platform != "win32":
    raise SystemExit("DroidWebDisplayWindows.spec is a Windows-only target")

ROOT = Path(SPECPATH).resolve().parents[1]
ADB_DIR = Path(os.environ["DWD_ADB_DIR"]).resolve()
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
parts = [int(part) for part in VERSION.split(".")]
if len(parts) != 3:
    raise SystemExit(f"Expected semantic VERSION, got {VERSION!r}")
numeric_version = (*parts, 0)

ICON = ROOT / "packaging" / "windows" / "droidwebdisplay.ico"
ICON.write_bytes(base64.b64decode((ICON.with_suffix(".ico.base64")).read_text(encoding="ascii")))

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

adb_names = ["adb.exe", "AdbWinApi.dll", "AdbWinUsbApi.dll"]
adb_binaries = [(str(ADB_DIR / name), "adb") for name in adb_names if (ADB_DIR / name).is_file()]
if not any(Path(source).name.lower() == "adb.exe" for source, _ in adb_binaries):
    raise SystemExit(f"ADB executable missing from {ADB_DIR}")

server_dir = ROOT / "server"
if not server_dir.is_dir():
    raise SystemExit("server directory is missing; run tools/download_server.py first")

hiddenimports = sorted(set(collect_submodules("uvicorn") + collect_submodules("websockets")))
datas = [
    (str(ROOT / "apps" / "web-client" / "dist"), "apps/web-client/dist"),
    (str(ROOT / "apps" / "web-client" / "dist-manifest.json"), "apps/web-client"),
    (str(ROOT / "packages" / "scrcpy-protocol" / "dist"), "packages/scrcpy-protocol/dist"),
    (str(ROOT / "packages" / "scrcpy-protocol" / "package.json"), "packages/scrcpy-protocol"),
    (str(ROOT / "compatibility"), "compatibility"),
    (str(server_dir), "server"),
    (str(ROOT / "VERSION"), "."),
    (str(ROOT / "LICENSE"), "."),
    (str(ROOT / "THIRD_PARTY_NOTICES.md"), "."),
    (str(ROOT / "SECURITY.md"), "."),
]

a = Analysis(
    [str(ROOT / "tools" / "desktop_entry.py")],
    pathex=[str(ROOT), str(ROOT / "tools")],
    binaries=adb_binaries,
    datas=datas,
    hiddenimports=hiddenimports,
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
    a.datas,
    [],
    name="DroidWebDisplay",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ICON),
    version=version_info,
)
