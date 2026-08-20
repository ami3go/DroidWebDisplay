"""Shared inputs for the DroidWebDisplay PyInstaller specs.

The three specs (Linux, Windows onefile, Windows onedir) previously repeated
the bundled-data list, the ADB discovery and the hidden-import computation
verbatim. Adding a bundled file meant editing three places, and missing one
produced a package broken on a single platform only.

Spec files are exec'd rather than imported, so they reach this module by
putting SPECPATH on sys.path. Nothing here is imported by the application: it
runs at spec-evaluation time only.
"""

from __future__ import annotations

from pathlib import Path
import os
import re

from PyInstaller.utils.hooks import collect_submodules

ENTRY_SCRIPT = ("tools", "desktop_entry.py")


def repo_root(specpath: str) -> Path:
    return Path(specpath).resolve().parents[1]


def adb_dir() -> Path:
    """The platform-tools directory, supplied by CI as DWD_ADB_DIR."""
    return Path(os.environ["DWD_ADB_DIR"]).resolve()


def adb_binaries(directory: Path, *, windows: bool) -> list[tuple[str, str]]:
    """ADB files to bundle, failing loudly when the executable is absent.

    A missing adb produces a package that looks fine until a user plugs in a
    phone, so this is a build-time error rather than a warning.
    """
    names = ["adb.exe", "AdbWinApi.dll", "AdbWinUsbApi.dll"] if windows else ["adb"]
    found = [(str(directory / name), "adb") for name in names if (directory / name).is_file()]
    executable = "adb.exe" if windows else "adb"
    if not any(Path(source).name.lower() == executable for source, _ in found):
        raise SystemExit(f"ADB executable missing from {directory}")
    return found


def bundle_datas(root: Path) -> list[tuple[str, str]]:
    """Data files every platform package ships.

    Keep this the single definition: a file added to one spec and not the
    others yields a package that is broken on one platform only.
    """
    server_dir = root / "server"
    if not server_dir.is_dir():
        raise SystemExit("server directory is missing; run tools/download_server.py first")
    return [
        (str(root / "apps" / "web-client" / "dist"), "apps/web-client/dist"),
        (str(root / "apps" / "web-client" / "dist-manifest.json"), "apps/web-client"),
        (str(root / "packages" / "scrcpy-protocol" / "dist"), "packages/scrcpy-protocol/dist"),
        (str(root / "packages" / "scrcpy-protocol" / "package.json"), "packages/scrcpy-protocol"),
        (str(root / "compatibility"), "compatibility"),
        (str(server_dir), "server"),
        (str(root / "VERSION"), "."),
        (str(root / "LICENSE"), "."),
        (str(root / "THIRD_PARTY_NOTICES.md"), "."),
        (str(root / "SECURITY.md"), "."),
    ]


def hidden_imports() -> list[str]:
    return sorted(set(collect_submodules("uvicorn") + collect_submodules("websockets")))


def read_version(root: Path) -> tuple[str, tuple[int, int, int, int]]:
    """Return the VERSION text and the four-int tuple Windows resources need.

    The VS_FIXEDFILEINFO field takes integers, so a prerelease suffix has to be
    stripped. Parsing the whole string with int() raised on the first -rc, and
    this project has published -rc tags.
    """
    text = (root / "VERSION").read_text(encoding="utf-8").strip()
    core = re.match(r"^(\d+)\.(\d+)\.(\d+)", text)
    if not core:
        raise SystemExit(f"Expected VERSION to start with MAJOR.MINOR.PATCH, got {text!r}")
    return text, (int(core.group(1)), int(core.group(2)), int(core.group(3)), 0)


def windows_icon(root: Path, workdir: Path) -> Path:
    """Decode the tracked base64 icon into the build directory.

    Writing it back into packaging/windows/ left an untracked binary in the
    checkout after every build.
    """
    workdir.mkdir(parents=True, exist_ok=True)
    icon = workdir / "droidwebdisplay.ico"
    source = root / "packaging" / "windows" / "droidwebdisplay.ico.base64"
    import base64

    icon.write_bytes(base64.b64decode(source.read_text(encoding="ascii")))
    return icon
