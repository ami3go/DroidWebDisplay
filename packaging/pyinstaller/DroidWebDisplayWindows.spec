# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import base64
import os
import re
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
# The Windows VS_FIXEDFILEINFO field takes four integers, so a prerelease
# suffix has to be stripped before parsing. int() on "8-rc.1" raises, which
# would have failed the build outright the first time VERSION carried one --
# and this project has already published -rc tags.
core = re.match(r"^(\d+)\.(\d+)\.(\d+)", VERSION)
if not core:
    raise SystemExit(f"Expected VERSION to start with MAJOR.MINOR.PATCH, got {VERSION!r}")
numeric_version = (int(core.group(1)), int(core.group(2)), int(core.group(3)), 0)

# Decode the tracked base64 icon into PyInstaller's work directory rather than
# back into packaging/windows/. Writing it into the source tree left an
# untracked binary behind after every build, which `git add -A` would commit.
ICON_SOURCE = ROOT / "packaging" / "windows" / "droidwebdisplay.ico.base64"
ICON_DIR = Path(globals().get("workpath") or (ROOT / "build"))
ICON_DIR.mkdir(parents=True, exist_ok=True)
ICON = ICON_DIR / "droidwebdisplay.ico"
ICON.write_bytes(base64.b64decode(ICON_SOURCE.read_text(encoding="ascii")))

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
