#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"Expected text not found in {path}: {old[:120]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


def append_once(path: str, marker: str, addition: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    if addition.strip() in text:
        return
    if marker not in text:
        raise SystemExit(f"Append marker not found in {path}: {marker!r}")
    target.write_text(text.replace(marker, marker + addition, 1), encoding="utf-8")


def make_ico(path: Path) -> None:
    """Generate a deterministic multi-size ICO matching the existing phone favicon."""

    def image(size: int) -> bytes:
        width = height = size
        rgba = bytearray(width * height * 4)

        def blend_pixel(x: int, y: int, r: int, g: int, b: int, a: int = 255) -> None:
            if 0 <= x < width and 0 <= y < height:
                i = (y * width + x) * 4
                rgba[i : i + 4] = bytes((b, g, r, a))

        def rounded_rect(x0: float, y0: float, x1: float, y1: float, radius: float, color: tuple[int, int, int, int]) -> None:
            for y in range(height):
                py = y + 0.5
                for x in range(width):
                    px = x + 0.5
                    cx = min(max(px, x0 + radius), x1 - radius)
                    cy = min(max(py, y0 + radius), y1 - radius)
                    if (px - cx) ** 2 + (py - cy) ** 2 <= radius ** 2 and x0 <= px <= x1 and y0 <= py <= y1:
                        blend_pixel(x, y, *color)

        s = size / 64.0
        rounded_rect(12*s, 2*s, 52*s, 62*s, 9*s, (93, 124, 255, 255))
        rounded_rect(17*s, 10*s, 47*s, 50*s, 4*s, (10, 13, 19, 255))
        rounded_rect(26*s, 6*s, 38*s, 8.5*s, 1.25*s, (220, 228, 255, 255))
        cx, cy, rr = 32*s, 56*s, 2.5*s
        for y in range(height):
            for x in range(width):
                if (x + 0.5 - cx) ** 2 + (y + 0.5 - cy) ** 2 <= rr ** 2:
                    blend_pixel(x, y, 243, 246, 251, 255)

        # ICO BMP stores rows bottom-up. Height is doubled to include the 1-bit AND mask.
        dib = struct.pack(
            "<IIIHHIIIIII",
            40, width, height * 2, 1, 32, 0, width * height * 4, 0, 0, 0, 0,
        )
        xor = bytearray()
        for y in range(height - 1, -1, -1):
            start = y * width * 4
            xor += rgba[start : start + width * 4]
        mask_stride = ((width + 31) // 32) * 4
        and_mask = bytes(mask_stride * height)
        return dib + xor + and_mask

    sizes = [16, 32, 48, 64, 128, 256]
    payloads = [image(size) for size in sizes]
    header = struct.pack("<HHH", 0, 1, len(sizes))
    directory = bytearray()
    offset = 6 + 16 * len(sizes)
    for size, payload in zip(sizes, payloads):
        wh = 0 if size == 256 else size
        directory += struct.pack("<BBBBHHII", wh, wh, 0, 0, 1, 32, len(payload), offset)
        offset += len(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(header + directory + b"".join(payloads))


# ---------------------------------------------------------------------------
# Windows PyInstaller resources and stable onedir package
# ---------------------------------------------------------------------------
spec = ROOT / "packaging/pyinstaller/DroidWebDisplay.spec"
spec.write_text(r'''# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import os
import sys

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).resolve().parents[1]
ADB_DIR = Path(os.environ["DWD_ADB_DIR"]).resolve()


def windows_version_info():
    if sys.platform != "win32":
        return None
    from PyInstaller.utils.win32.versioninfo import (
        FixedFileInfo,
        StringFileInfo,
        StringStruct,
        StringTable,
        VarFileInfo,
        VarStruct,
        VSVersionInfo,
    )

    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    values = [int(part) for part in version.split(".")]
    if len(values) != 3:
        raise SystemExit(f"Expected semantic VERSION, got {version!r}")
    numeric = (*values, 0)
    return VSVersionInfo(
        ffi=FixedFileInfo(
            filevers=numeric,
            prodvers=numeric,
            mask=0x3F,
            flags=0x0,
            OS=0x40004,
            fileType=0x1,
            subtype=0x0,
            date=(0, 0),
        ),
        kids=[
            StringFileInfo([
                StringTable(
                    "040904B0",
                    [
                        StringStruct("CompanyName", "DroidWebDisplay contributors"),
                        StringStruct("FileDescription", "DroidWebDisplay Android web display"),
                        StringStruct("FileVersion", version),
                        StringStruct("InternalName", "DroidWebDisplay"),
                        StringStruct("LegalCopyright", "Copyright DroidWebDisplay contributors"),
                        StringStruct("OriginalFilename", "DroidWebDisplay.exe"),
                        StringStruct("ProductName", "DroidWebDisplay"),
                        StringStruct("ProductVersion", version),
                    ],
                )
            ]),
            VarFileInfo([VarStruct("Translation", [1033, 1200])]),
        ],
    )


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
        upx=False,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=str(ROOT / "packaging" / "windows" / "droidwebdisplay.ico"),
        version=windows_version_info(),
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
''', encoding="utf-8")

onedir = ROOT / "packaging/pyinstaller/DroidWebDisplayOnedir.spec"
onedir.write_text(r'''# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import os
import sys

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).resolve().parents[1]
ADB_DIR = Path(os.environ["DWD_ADB_DIR"]).resolve()

if sys.platform != "win32":
    raise SystemExit("DroidWebDisplayOnedir.spec is a Windows distribution target")

from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo,
    StringFileInfo,
    StringStruct,
    StringTable,
    VarFileInfo,
    VarStruct,
    VSVersionInfo,
)

version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
parts = [int(part) for part in version.split(".")]
if len(parts) != 3:
    raise SystemExit(f"Expected semantic VERSION, got {version!r}")
numeric = (*parts, 0)
version_info = VSVersionInfo(
    ffi=FixedFileInfo(filevers=numeric, prodvers=numeric, mask=0x3F, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
    kids=[
        StringFileInfo([StringTable("040904B0", [
            StringStruct("CompanyName", "DroidWebDisplay contributors"),
            StringStruct("FileDescription", "DroidWebDisplay Android web display"),
            StringStruct("FileVersion", version),
            StringStruct("InternalName", "DroidWebDisplay"),
            StringStruct("LegalCopyright", "Copyright DroidWebDisplay contributors"),
            StringStruct("OriginalFilename", "DroidWebDisplay.exe"),
            StringStruct("ProductName", "DroidWebDisplay"),
            StringStruct("ProductVersion", version),
        ])]),
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
    icon=str(ROOT / "packaging" / "windows" / "droidwebdisplay.ico"),
    version=version_info,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="DroidWebDisplayOnedir",
)
''', encoding="utf-8")
make_ico(ROOT / "packaging/windows/droidwebdisplay.ico")

# ---------------------------------------------------------------------------
# Desktop package self-tests: validate the bundled ADB from inside both bundle modes.
# ---------------------------------------------------------------------------
replace_once(
    "tools/desktop_entry.py",
    '    parser.add_argument("--desktop-smoke", action="store_true", help=argparse.SUPPRESS)\n',
    '    parser.add_argument("--desktop-smoke", action="store_true", help=argparse.SUPPRESS)\n'
    '    parser.add_argument("--adb-smoke", action="store_true", help=argparse.SUPPRESS)\n',
)
replace_once(
    "tools/desktop_entry.py",
    '    args, server_args = _desktop_parser().parse_known_args(argv)\n\n    from run_bridge_service import BridgeServiceRuntime, main as bridge_main\n',
    '    args, server_args = _desktop_parser().parse_known_args(argv)\n\n'
    '    if args.adb_smoke:\n'
    '        import subprocess\n\n'
    '        adb = paths.adb_executable\n'
    '        if not isinstance(adb, Path) or not adb.is_file():\n'
    '            return 3\n'
    '        kwargs: dict[str, object] = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "check": False}\n'
    '        if os.name == "nt":\n'
    '            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)\n'
    '        try:\n'
    '            result = subprocess.run([str(adb), "version"], **kwargs)\n'
    '        except OSError:\n'
    '            return 4\n'
    '        return int(result.returncode)\n\n'
    '    from run_bridge_service import BridgeServiceRuntime, main as bridge_main\n',
)

# ---------------------------------------------------------------------------
# Device-state guidance for the common Windows ADB failure modes.
# ---------------------------------------------------------------------------
replace_once(
    "apps/web-client/src/controller.ts",
    '    this.updateClipboardUi();\n    await this.refreshDevices();\n    await this.refreshVirtualCapabilities();\n    this.updateDisplayUi();\n    this.setStatus("Ready", "Select an authorized Android device and connect.");\n',
    '    this.updateClipboardUi();\n    this.setStatus("Ready", "Select an authorized Android device and connect.");\n    await this.refreshDevices();\n    await this.refreshVirtualCapabilities();\n    this.updateDisplayUi();\n',
)
replace_once(
    "apps/web-client/src/controller.ts",
    '    this.#deviceListRefreshedAt = Date.now();\n    this.updateConnectAvailability();\n  }\n\n  public async connect(): Promise<void> {\n',
    '    this.#deviceListRefreshedAt = Date.now();\n    this.updateConnectAvailability();\n\n'
    '    const readyDevices = response.devices.filter((device) => device.ready);\n'
    '    if (!readyDevices.length) {\n'
    '      const blocked = response.devices.find((device) => device.authorizationRequired);\n'
    '      const noPermissions = response.devices.find((device) => device.state === "no permissions");\n'
    '      const offline = response.devices.find((device) => device.state === "offline");\n'
    '      if (blocked) {\n'
    '        this.setStatus("USB authorization required", `Unlock ${blocked.model ?? "the Android device"}, accept “Allow USB debugging?”, then refresh devices.`);\n'
    '      } else if (noPermissions) {\n'
    '        this.setStatus("ADB access blocked", "The device is visible but ADB cannot access it. On Windows, install/update the phone OEM USB driver and reconnect the cable.");\n'
    '      } else if (offline) {\n'
    '        this.setStatus("ADB device offline", "Reconnect USB, unlock the phone, and toggle USB debugging if the device remains offline.");\n'
    '      } else if (!response.devices.length) {\n'
    '        this.setStatus("No Android device", "Connect the phone by USB with USB debugging enabled. Windows may require the manufacturer USB driver.");\n'
    '      } else {\n'
    '        this.setStatus("ADB device not ready", `Device state: ${response.devices[0]!.state}. Resolve the Android/USB state and refresh devices.`);\n'
    '      }\n'
    '    } else {\n'
    '      const android16 = readyDevices.find((device) => Number.parseInt(device.android_version?.split(".")[0] ?? "", 10) >= 16);\n'
    '      if (android16) {\n'
    '        this.setStatus("Ready · Android 16", `${android16.model ?? android16.serial} is connected. If scrcpy reports IDisplayWindowListener/AbstractMethodError, DWD will classify it as an upstream Android 16 compatibility failure.`);\n'
    '      }\n'
    '    }\n'
    '  }\n\n  public async connect(): Promise<void> {\n',
)

# ---------------------------------------------------------------------------
# Browser/GPU diagnostics for black-video reports.
# ---------------------------------------------------------------------------
(ROOT / "apps/web-client/src/browser-support.ts").write_text(r'''export interface BrowserCapabilityReport {
  readonly supported: boolean;
  readonly missing: readonly string[];
  readonly userAgent: string;
  readonly browserName: string;
  readonly platform: string;
  readonly hardwareConcurrency: number | null;
  readonly secureContext: boolean | null;
  readonly gpuRenderer: string;
  readonly audioSupported: boolean;
  readonly missingAudio: readonly string[];
}

export interface BrowserCapabilityScope {
  readonly WebSocket?: unknown;
  readonly ReadableStream?: unknown;
  readonly WritableStream?: unknown;
  readonly VideoDecoder?: unknown;
  readonly EncodedVideoChunk?: unknown;
  readonly AudioDecoder?: unknown;
  readonly EncodedAudioChunk?: unknown;
  readonly AudioContext?: unknown;
  readonly navigator?: {
    readonly userAgent?: string;
    readonly platform?: string;
    readonly hardwareConcurrency?: number;
  };
  readonly isSecureContext?: boolean;
  readonly document?: Document;
}

export function browserName(userAgent: string): string {
  const matchers: readonly [RegExp, string][] = [
    [/Edg\/([0-9.]+)/, "Edge"],
    [/Chrome\/([0-9.]+)/, "Chrome"],
    [/Firefox\/([0-9.]+)/, "Firefox"],
    [/Version\/([0-9.]+).*Safari\//, "Safari"],
  ];
  for (const [pattern, name] of matchers) {
    const match = pattern.exec(userAgent);
    if (match) return `${name} ${match[1]}`;
  }
  return userAgent === "unknown" ? "unknown" : "Other browser";
}

function inspectGpuRenderer(scope: BrowserCapabilityScope): string {
  try {
    const canvas = scope.document?.createElement("canvas") as HTMLCanvasElement | undefined;
    const gl = canvas?.getContext("webgl") ?? canvas?.getContext("experimental-webgl");
    if (!gl || !(gl instanceof WebGLRenderingContext)) return "unavailable";
    const debug = gl.getExtension("WEBGL_debug_renderer_info") as { readonly UNMASKED_RENDERER_WEBGL: number } | null;
    const renderer = gl.getParameter(debug?.UNMASKED_RENDERER_WEBGL ?? gl.RENDERER);
    return typeof renderer === "string" && renderer.trim() ? renderer.trim() : "available";
  } catch {
    return "unavailable";
  }
}

export function inspectBrowserCapabilities(scope: BrowserCapabilityScope = globalThis): BrowserCapabilityReport {
  const required = ["WebSocket", "ReadableStream", "WritableStream", "VideoDecoder", "EncodedVideoChunk"] as const;
  const missing = required.filter((name) => typeof scope[name] === "undefined");
  const audio = ["AudioDecoder", "EncodedAudioChunk", "AudioContext"] as const;
  const missingAudio = audio.filter((name) => typeof scope[name] === "undefined");
  const userAgent = scope.navigator?.userAgent ?? "unknown";
  const concurrency = scope.navigator?.hardwareConcurrency;
  return {
    supported: missing.length === 0,
    missing,
    userAgent,
    browserName: browserName(userAgent),
    platform: scope.navigator?.platform || "unknown",
    hardwareConcurrency: typeof concurrency === "number" && Number.isFinite(concurrency) ? concurrency : null,
    secureContext: typeof scope.isSecureContext === "boolean" ? scope.isSecureContext : null,
    gpuRenderer: inspectGpuRenderer(scope),
    audioSupported: missingAudio.length === 0,
    missingAudio,
  };
}
''', encoding="utf-8")

replace_once(
    "apps/web-client/src/main.ts",
    '  const capabilities = inspectBrowserCapabilities();\n  const unsupported = required<HTMLElement>("#unsupported");\n',
    '  const capabilities = inspectBrowserCapabilities();\n'
    '  required<HTMLElement>("#diagnostic-browser").textContent = `${capabilities.browserName} · ${capabilities.platform}`;\n'
    '  required<HTMLElement>("#diagnostic-webcodecs").textContent = capabilities.supported ? "VideoDecoder ready" : `Missing ${capabilities.missing.join(", ")}`;\n'
    '  const gpu = required<HTMLElement>("#diagnostic-gpu");\n'
    '  gpu.textContent = capabilities.gpuRenderer.length > 70 ? `${capabilities.gpuRenderer.slice(0, 67)}…` : capabilities.gpuRenderer;\n'
    '  gpu.title = capabilities.gpuRenderer;\n'
    '  required<HTMLElement>("#diagnostic-environment").textContent = `${capabilities.hardwareConcurrency ?? "?"} logical CPU · ${capabilities.secureContext === false ? "non-secure context" : "secure/local context"}`;\n'
    '  const unsupported = required<HTMLElement>("#unsupported");\n',
)
replace_once(
    "apps/web-client/static/index.html",
    '            <div><span>Free RAM</span><strong id="diagnostic-ram">—</strong></div>\n          </div>\n          <div id="statistics" class="statistics">No video statistics</div>\n',
    '            <div><span>Free RAM</span><strong id="diagnostic-ram">—</strong></div>\n'
    '            <div><span>Browser</span><strong id="diagnostic-browser">—</strong></div>\n'
    '            <div><span>WebCodecs</span><strong id="diagnostic-webcodecs">—</strong></div>\n'
    '            <div><span>GPU</span><strong id="diagnostic-gpu">—</strong></div>\n'
    '            <div><span>Environment</span><strong id="diagnostic-environment">—</strong></div>\n'
    '          </div>\n'
    '          <div id="statistics" class="statistics">No video statistics</div>\n'
    '          <p id="diagnostic-video-help" class="explorer-help">Black video while controls still work: update Chrome/Edge and the GPU driver; if it persists, disable browser hardware acceleration, restart the browser, and reconnect.</p>\n',
)

append_once(
    "apps/web-client/tests/browser-support.test.mjs",
    'import { inspectBrowserCapabilities } from "../dist/assets/browser-support.js";\n',
    'import { browserName } from "../dist/assets/browser-support.js";\n',
)
append_once(
    "apps/web-client/tests/browser-support.test.mjs",
    'test("reports all mandatory Chromium/WebCodecs capabilities", () => {\n',
    '''\ntest("extracts useful browser identity for Windows diagnostics", () => {\n  assert.equal(browserName("Mozilla/5.0 Chrome/150.0.0.0 Safari/537.36"), "Chrome 150.0.0.0");\n  assert.equal(browserName("Mozilla/5.0 Chrome/150.0.0.0 Safari/537.36 Edg/150.0.0.0"), "Edge 150.0.0.0");\n});\n\n''',
)

# ---------------------------------------------------------------------------
# Android 16 upstream server failure classification.
# ---------------------------------------------------------------------------
replace_once(
    "droid_web_display/scrcpy/session.py",
    'from typing import Awaitable, Callable\n',
    'from typing import Awaitable, Callable, Iterable\n',
)
replace_once(
    "droid_web_display/scrcpy/session.py",
    'MAX_RETAINED_TERMINATED_SESSIONS = 20\n\n\n\nclass PrefixedStreamReader:',
    'MAX_RETAINED_TERMINATED_SESSIONS = 20\n'
    'ANDROID16_DISPLAY_LISTENER_FAILURE = "android16_display_listener_incompatibility"\n\n\n'
    'def classify_scrcpy_server_failure(lines: Iterable[str]) -> str | None:\n'
    '    text = "\\n".join(lines)\n'
    '    if "AbstractMethodError" in text and "IDisplayWindowListener" in text:\n'
    '        return ANDROID16_DISPLAY_LISTENER_FAILURE\n'
    '    return None\n\n\n'
    'class PrefixedStreamReader:',
)
replace_once(
    "droid_web_display/scrcpy/session.py",
    '        except Exception as exc:\n'
    '            session.state = SessionState.FAILED\n'
    '            session.error = str(exc)\n'
    '            session.stop_reason = "start_failed"\n'
    '            await self._cleanup_session_resources(session)\n'
    '            await self._retire_session(session)\n'
    '            if isinstance(exc, SessionError):\n'
    '                raise\n'
    '            raise SessionError(\n'
    '                f"Unable to start scrcpy session: {exc}",\n'
    '                details={\n'
    '                    "sessionId": session.session_id,\n'
    '                    "serial": session.serial,\n'
    '                    "serverArguments": list(session.server_arguments),\n'
    '                    "serverLog": list(session.server_log),\n'
    '                    "classification": session.virtual_display_failure_classification,\n'
    '                },\n'
    '            ) from exc\n',
    '        except Exception as exc:\n'
    '            server_log = list(session.server_log)\n'
    '            server_failure = classify_scrcpy_server_failure(server_log)\n'
    '            session.state = SessionState.FAILED\n'
    '            session.error = str(exc)\n'
    '            session.stop_reason = "start_failed"\n'
    '            await self._cleanup_session_resources(session)\n'
    '            await self._retire_session(session)\n'
    '            if isinstance(exc, SessionError):\n'
    '                raise\n'
    '            if server_failure == ANDROID16_DISPLAY_LISTENER_FAILURE:\n'
    '                raise SessionError(\n'
    '                    "scrcpy server hit a known Android 16 display-listener incompatibility",\n'
    '                    details={\n'
    '                        "sessionId": session.session_id,\n'
    '                        "serial": session.serial,\n'
    '                        "classification": server_failure,\n'
    '                        "serverLog": server_log,\n'
    '                        "guidance": "This is an upstream scrcpy server compatibility failure, not a Windows renderer failure. Preserve the current DWD adapter and use a device/Android build that is not affected until a newer scrcpy adapter is promoted through the DWD compatibility gate.",\n'
    '                    },\n'
    '                ) from exc\n'
    '            raise SessionError(\n'
    '                f"Unable to start scrcpy session: {exc}",\n'
    '                details={\n'
    '                    "sessionId": session.session_id,\n'
    '                    "serial": session.serial,\n'
    '                    "serverArguments": list(session.server_arguments),\n'
    '                    "serverLog": server_log,\n'
    '                    "classification": session.virtual_display_failure_classification,\n'
    '                },\n'
    '            ) from exc\n',
)

(ROOT / "tests/regression/test_scrcpy_android16_failure_classification.py").write_text('''from droid_web_display.scrcpy.session import (\n    ANDROID16_DISPLAY_LISTENER_FAILURE,\n    classify_scrcpy_server_failure,\n)\n\n\ndef test_android16_display_listener_failure_is_classified() -> None:\n    log = [\n        "[server] ERROR: Exception on binder thread",\n        "java.lang.AbstractMethodError: android.view.IDisplayWindowListener.onDisplayAnimationsDisabledChanged",\n    ]\n    assert classify_scrcpy_server_failure(log) == ANDROID16_DISPLAY_LISTENER_FAILURE\n\n\ndef test_unrelated_server_failure_is_not_misclassified() -> None:\n    assert classify_scrcpy_server_failure(["ERROR: encoder unavailable"]) is None\n''', encoding="utf-8")

# ---------------------------------------------------------------------------
# CI: build and smoke both Windows distribution forms, verify PE metadata,
# execute bundled ADB, and exercise repeated start/stop cleanup.
# ---------------------------------------------------------------------------
old_windows = '''      - name: Build Windows executable\n        run: python -m PyInstaller --noconfirm --clean packaging/pyinstaller/DroidWebDisplay.spec\n      - name: Smoke-test Windows desktop host\n        shell: pwsh\n        run: |\n          $process = Start-Process -FilePath ".\\dist\\DroidWebDisplay.exe" -ArgumentList "--desktop-smoke" -Wait -PassThru\n          if ($process.ExitCode -ne 0) { exit $process.ExitCode }\n      - name: Smoke-test Windows executable CLI\n        shell: pwsh\n        run: |\n          $process = Start-Process -FilePath ".\\dist\\DroidWebDisplay.exe" -ArgumentList "--help" -Wait -PassThru\n          if ($process.ExitCode -ne 0) { exit $process.ExitCode }\n      - name: Smoke-test Windows executable service\n        run: python tools/smoke_desktop_package.py .\\dist\\DroidWebDisplay.exe --timeout 60\n      - uses: actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02 # v4\n        with:\n          name: windows-package-smoke\n          path: dist/DroidWebDisplay.exe\n          if-no-files-found: error\n'''
new_windows = '''      - name: Build Windows portable executable\n        run: python -m PyInstaller --noconfirm --clean packaging/pyinstaller/DroidWebDisplay.spec\n      - name: Build Windows stable onedir package\n        run: python -m PyInstaller --noconfirm --clean packaging/pyinstaller/DroidWebDisplayOnedir.spec\n      - name: Verify Windows metadata and bundled ADB\n        shell: pwsh\n        run: |\n          $version = (Get-Content VERSION -Raw).Trim()\n          $packages = @(\n            ".\\dist\\DroidWebDisplay.exe",\n            ".\\dist\\DroidWebDisplayOnedir\\DroidWebDisplay.exe"\n          )\n          foreach ($path in $packages) {\n            $info = (Get-Item $path).VersionInfo\n            if ($info.ProductName -ne "DroidWebDisplay") { throw "ProductName missing from $path" }\n            if (-not $info.FileVersion.StartsWith($version)) { throw "FileVersion $($info.FileVersion) does not match $version in $path" }\n            if (-not $info.ProductVersion.StartsWith($version)) { throw "ProductVersion $($info.ProductVersion) does not match $version in $path" }\n            if ($info.OriginalFilename -ne "DroidWebDisplay.exe") { throw "OriginalFilename missing from $path" }\n          }\n          $adb = Get-ChildItem ".\\dist\\DroidWebDisplayOnedir" -Recurse -Filter adb.exe | Select-Object -First 1\n          if (-not $adb) { throw "Bundled adb.exe missing from onedir package" }\n          & $adb.FullName version\n          if ($LASTEXITCODE -ne 0) { throw "Bundled adb.exe failed to execute" }\n      - name: Smoke-test Windows portable desktop, CLI and ADB\n        shell: pwsh\n        run: |\n          foreach ($arg in @("--desktop-smoke", "--help", "--adb-smoke")) {\n            $process = Start-Process -FilePath ".\\dist\\DroidWebDisplay.exe" -ArgumentList $arg -Wait -PassThru\n            if ($process.ExitCode -ne 0) { throw "Portable smoke $arg failed: $($process.ExitCode)" }\n          }\n      - name: Smoke-test Windows onedir desktop, CLI and ADB\n        shell: pwsh\n        run: |\n          $exe = ".\\dist\\DroidWebDisplayOnedir\\DroidWebDisplay.exe"\n          foreach ($arg in @("--desktop-smoke", "--help", "--adb-smoke")) {\n            $process = Start-Process -FilePath $exe -ArgumentList $arg -Wait -PassThru\n            if ($process.ExitCode -ne 0) { throw "Onedir smoke $arg failed: $($process.ExitCode)" }\n          }\n      - name: Repeat Windows service start-stop smoke\n        shell: pwsh\n        run: |\n          1..3 | ForEach-Object { python tools/smoke_desktop_package.py .\\dist\\DroidWebDisplay.exe --timeout 60 }\n          1..3 | ForEach-Object { python tools/smoke_desktop_package.py .\\dist\\DroidWebDisplayOnedir\\DroidWebDisplay.exe --timeout 60 }\n      - name: Build Windows onedir ZIP\n        shell: pwsh\n        run: Compress-Archive -Path ".\\dist\\DroidWebDisplayOnedir\\*" -DestinationPath ".\\dist\\DroidWebDisplay-windows-x86_64.zip" -CompressionLevel Optimal\n      - uses: actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02 # v4\n        with:\n          name: windows-package-smoke\n          path: |\n            dist/DroidWebDisplay.exe\n            dist/DroidWebDisplay-windows-x86_64.zip\n          if-no-files-found: error\n'''
replace_once(".github/workflows/ci.yml", old_windows, new_windows)

replace_once(
    ".github/workflows/release.yml",
    '          windows=$(find artifacts/windows -type f -name \'DroidWebDisplay.exe\' -print -quit)\n'
    '          linux=$(find artifacts/linux -type f -name \'*.AppImage\' -print -quit)\n'
    '          test -n "$windows"\n'
    '          test -n "$linux"\n\n'
    '          cp "$windows" "release-assets/DroidWebDisplay-v${RELEASE_VERSION}-windows-x86_64.exe"\n'
    '          cp "$linux" "release-assets/DroidWebDisplay-v${RELEASE_VERSION}-linux-x86_64.AppImage"\n',
    '          windows=$(find artifacts/windows -type f -name \'DroidWebDisplay.exe\' -print -quit)\n'
    '          windows_zip=$(find artifacts/windows -type f -name \'DroidWebDisplay-windows-x86_64.zip\' -print -quit)\n'
    '          linux=$(find artifacts/linux -type f -name \'*.AppImage\' -print -quit)\n'
    '          test -n "$windows"\n'
    '          test -n "$windows_zip"\n'
    '          test -n "$linux"\n\n'
    '          cp "$windows" "release-assets/DroidWebDisplay-v${RELEASE_VERSION}-windows-x86_64.exe"\n'
    '          cp "$windows_zip" "release-assets/DroidWebDisplay-v${RELEASE_VERSION}-windows-x86_64.zip"\n'
    '          cp "$linux" "release-assets/DroidWebDisplay-v${RELEASE_VERSION}-linux-x86_64.AppImage"\n',
)
replace_once(
    ".github/workflows/release.yml",
    '            release-assets/DroidWebDisplay-v${RELEASE_VERSION}-windows-x86_64.exe \\\n            release-assets/DroidWebDisplay-v${RELEASE_VERSION}-linux-x86_64.AppImage \\\n',
    '            release-assets/DroidWebDisplay-v${RELEASE_VERSION}-windows-x86_64.exe \\\n            release-assets/DroidWebDisplay-v${RELEASE_VERSION}-windows-x86_64.zip \\\n            release-assets/DroidWebDisplay-v${RELEASE_VERSION}-linux-x86_64.AppImage \\\n',
)

# ---------------------------------------------------------------------------
# Regression guards and operator documentation.
# ---------------------------------------------------------------------------
(ROOT / "tests/packaging/test_windows_package_hardening.py").write_text(r'''from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_windows_pyinstaller_targets_are_uncompressed_and_versioned() -> None:
    portable = (ROOT / "packaging/pyinstaller/DroidWebDisplay.spec").read_text(encoding="utf-8")
    onedir = (ROOT / "packaging/pyinstaller/DroidWebDisplayOnedir.spec").read_text(encoding="utf-8")
    for text in (portable, onedir):
        assert "upx=False" in text
        assert "droidwebdisplay.ico" in text
        assert "ProductName" in text
        assert "DroidWebDisplay contributors" in text
    assert "runtime_tmpdir=None" in portable
    assert 'name="DroidWebDisplayOnedir"' in onedir


def test_windows_ci_builds_and_smokes_portable_and_onedir_packages() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "DroidWebDisplayOnedir.spec" in workflow
    assert "DroidWebDisplay-windows-x86_64.zip" in workflow
    assert "--adb-smoke" in workflow
    assert "Repeat Windows service start-stop smoke" in workflow
    assert "ProductName" in workflow


def test_release_pipeline_publishes_stable_windows_zip() -> None:
    workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    assert "DroidWebDisplay-v${RELEASE_VERSION}-windows-x86_64.zip" in workflow


def test_windows_adb_and_browser_failure_guidance_is_present() -> None:
    desktop = (ROOT / "tools/desktop_entry.py").read_text(encoding="utf-8")
    controller = (ROOT / "apps/web-client/src/controller.ts").read_text(encoding="utf-8")
    html = (ROOT / "apps/web-client/static/index.html").read_text(encoding="utf-8")
    assert '"--adb-smoke"' in desktop
    assert "USB authorization required" in controller
    assert "manufacturer USB driver" in controller
    assert "Android 16" in controller
    assert "disable browser hardware acceleration" in html
    assert 'id="diagnostic-gpu"' in html
''', encoding="utf-8")

(ROOT / "docs/WINDOWS_PACKAGING.md").write_text('''# Windows packaging and troubleshooting\n\nDroidWebDisplay ships two unsigned Windows distribution forms. Code signing is intentionally deferred; these packaging rules are independent of signing.\n\n## Distribution forms\n\n- **Portable EXE** — `DroidWebDisplay-vX.Y.Z-windows-x86_64.exe`. Convenient single-file launch. PyInstaller extracts this form to a temporary runtime directory while it is running.\n- **Stable onedir ZIP** — `DroidWebDisplay-vX.Y.Z-windows-x86_64.zip`. Recommended for long-running installations because dependencies live in a stable directory instead of a temporary `_MEI...` extraction tree. Extract the ZIP and run `DroidWebDisplay.exe`.\n\nBoth forms include the verified Android platform-tools ADB executable and DLLs, the verified scrcpy server, the web client, licenses, and identical application version metadata. UPX compression is disabled.\n\n## USB / ADB states\n\nDroidWebDisplay surfaces ADB states explicitly. `unauthorized`/`authorizing` means the phone must be unlocked and the **Allow USB debugging?** prompt accepted. `offline` usually needs a USB reconnect or USB-debugging reset. `no permissions` means host access is blocked; on Windows, install or update the phone manufacturer's USB driver.\n\n## Black video with working controls\n\nDroidWebDisplay uses browser WebCodecs rather than scrcpy's native Windows renderer. Diagnostics reports the browser, WebCodecs availability, platform and visible WebGL GPU renderer. If controls work but the picture remains black: update Chrome/Edge, update the GPU driver, then try disabling browser hardware acceleration and restart the browser.\n\n## Android 16 compatibility\n\nThe protected stable adapter remains scrcpy 4.1. Some Android 16 builds have produced an upstream `AbstractMethodError` involving `IDisplayWindowListener`. DroidWebDisplay classifies that server signature explicitly so it is not mistaken for a Windows packaging or GPU failure. The stable scrcpy adapter must not be replaced until the normal DWD compatibility and HIL gates prove an equal-or-better update.\n''', encoding="utf-8")

(ROOT / "docs/WINDOWS_RELEASE_HIL.md").write_text('''# Windows release HIL checklist\n\nRun this checklist on the exact packaged Windows artifact before promoting a release when hardware is available. CI covers package startup, repeated shutdown, bundled ADB execution, PE version metadata and service availability; these hardware/browser checks remain real-device qualification.\n\n- Start both the portable EXE and extracted onedir ZIP.\n- Verify the connected Android device transitions through ADB authorization correctly.\n- Connect physical display and confirm the first video frame without requiring Rotate.\n- Rotate twice and confirm video recovers without reconnecting.\n- Verify mouse/touch controls, PC keyboard input, Back/Home/Recent and power control.\n- Verify Android→PC automatic clipboard, Copy button and Ctrl+C.\n- Verify PC→Android automatic clipboard, Paste/Ctrl+V and Type; normal typing must remain usable.\n- Disconnect/reconnect and confirm clipboard/session state does not leak.\n- Transfer a file in both directions.\n- Leave a session active through Windows display-off and sleep/resume, then verify video/control reconnect.\n- Run a multi-hour soak and confirm no orphan `DroidWebDisplay.exe`, `adb.exe` or stale service remains after exit.\n- On at least one Android 16 device, confirm either normal operation or the explicit upstream display-listener classification.\n- If video is black with controls active, record browser version, GPU renderer and the result of toggling browser hardware acceleration.\n''', encoding="utf-8")

print("Windows package hardening patch applied")
