#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

PRODUCT_TITLE_MARKER = "<title>DroidWebDisplay</title>"
WEB_UI_MARKER = "droidwebdisplay-native-single-drawer-v1"


def _reserve_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _read_log(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Launch a frozen DroidWebDisplay package and probe its web UI")
    parser.add_argument("executable", type=Path)
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument("--appimage-extract-and-run", action="store_true")
    args = parser.parse_args()

    executable = args.executable.resolve()
    if not executable.is_file():
        print(f"ERROR: package executable does not exist: {executable}", file=sys.stderr)
        return 2

    port = _reserve_port()
    url = f"http://127.0.0.1:{port}/"

    with tempfile.TemporaryDirectory(prefix="dwd-package-smoke-") as temporary:
        temp_root = Path(temporary)
        stdout_path = temp_root / "stdout.log"
        stderr_path = temp_root / "stderr.log"
        environment = os.environ.copy()
        if os.name == "nt":
            environment["LOCALAPPDATA"] = str(temp_root / "LocalAppData")
        else:
            environment["XDG_STATE_HOME"] = str(temp_root / "state")
        if args.appimage_extract_and_run:
            environment["APPIMAGE_EXTRACT_AND_RUN"] = "1"

        command = [str(executable), "--no-browser", "--port", str(port)]
        print(f"Launching package smoke test: {' '.join(command)}")
        print(f"Probing: {url}")

        with stdout_path.open("w", encoding="utf-8") as stdout_handle, stderr_path.open(
            "w", encoding="utf-8"
        ) as stderr_handle:
            process = subprocess.Popen(
                command,
                stdout=stdout_handle,
                stderr=stderr_handle,
                env=environment,
                text=True,
            )

            deadline = time.monotonic() + args.timeout
            success = False
            last_error = "service did not become ready"
            try:
                while time.monotonic() < deadline:
                    return_code = process.poll()
                    if return_code is not None:
                        last_error = f"package exited before probe succeeded with code {return_code}"
                        break
                    try:
                        request = urllib.request.Request(
                            url,
                            headers={"User-Agent": "DroidWebDisplay-package-smoke/1"},
                        )
                        with urllib.request.urlopen(request, timeout=1.0) as response:
                            html = response.read(512 * 1024).decode("utf-8", errors="replace")
                        missing = [
                            marker
                            for marker in (PRODUCT_TITLE_MARKER, WEB_UI_MARKER)
                            if marker not in html
                        ]
                        if not missing:
                            success = True
                            break
                        last_error = f"web root is missing expected marker(s): {', '.join(missing)}"
                    except (urllib.error.URLError, OSError, ValueError) as exc:
                        last_error = str(exc)
                    time.sleep(0.25)
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=10)

        stdout_text = _read_log(stdout_path)
        stderr_text = _read_log(stderr_path)
        if success:
            print("PASS: packaged DroidWebDisplay started and served the current web UI markers")
            if stdout_text.strip():
                print("--- package stdout ---")
                print(stdout_text.rstrip())
            return 0

        print(f"FAIL: {last_error}", file=sys.stderr)
        if stdout_text.strip():
            print("--- package stdout ---", file=sys.stderr)
            print(stdout_text.rstrip(), file=sys.stderr)
        if stderr_text.strip():
            print("--- package stderr ---", file=sys.stderr)
            print(stderr_text.rstrip(), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
