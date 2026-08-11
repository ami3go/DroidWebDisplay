#!/usr/bin/env python3
from __future__ import annotations
import argparse
import os
from pathlib import Path
import signal
import subprocess
import time


def main() -> int:
    parser = argparse.ArgumentParser(description="Stop an installed Gpt-Bridge service by PID file")
    parser.add_argument("--pid-file", type=Path, default=Path("data/service.pid"))
    parser.add_argument("--timeout", type=float, default=5.0)
    args = parser.parse_args()
    path = args.pid_file.resolve()
    if not path.is_file():
        print("Gpt-Bridge is not running (PID file not present).")
        return 0
    try:
        pid = int(path.read_text(encoding="ascii").strip())
    except (OSError, ValueError):
        path.unlink(missing_ok=True)
        print("Removed invalid PID file.")
        return 0
    if os.name == "nt":
        result = subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], check=False)
        path.unlink(missing_ok=True)
        return 0 if result.returncode == 0 else result.returncode
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        path.unlink(missing_ok=True)
        return 0
    deadline = time.monotonic() + args.timeout
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            path.unlink(missing_ok=True)
            return 0
        time.sleep(0.1)
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    path.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
