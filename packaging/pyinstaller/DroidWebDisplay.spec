# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import os
import sys

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).resolve().parents[1]
ADB_DIR = Path(os.environ["DWD_ADB_DIR"]).resolve()

adb_names = ["adb.exe", "AdbWinApi.dll", "AdbWinUsbApi.dll"] if sys.platform == "win32" else ["adb"]
adb_binaries = [(str(ADB_DIR / name), "adb") for name in adb_names if (ADB_DIR / name).is_file()]
if not any(Path(source).name.lower() in {"adb", "adb.exe"} for source, _ in adb_binaries):
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

if sys.platform == "win32":
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
        upx=True,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=True,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name="DroidWebDisplay",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
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
        upx=True,
        upx_exclude=[],
        name="DroidWebDisplay",
    )
