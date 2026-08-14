#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys


def _resource_root() -> Path:
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        return Path(bundle_root).resolve()
    return Path(__file__).resolve().parents[1]


def _desktop_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="DroidWebDisplay desktop host",
        epilog=(
            "Additional unknown options are passed to the embedded DroidWebDisplay server "
            "(for example --port 8765)."
        ),
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run only the browser service, without the desktop GUI",
    )
    parser.add_argument("--no-browser", action="store_true", help="Do not open the browser automatically")
    parser.add_argument(
        "--open-browser",
        action="store_true",
        help="Open the browser when the server becomes ready",
    )
    parser.add_argument("--start-minimized", action="store_true", help="Start the desktop host minimized")
    parser.add_argument("--desktop-smoke", action="store_true", help=argparse.SUPPRESS)
    return parser


def main(argv: list[str] | None = None) -> int:
    resource_root = _resource_root()

    from droid_web_display.desktop.controller import DesktopPaths, ServerController
    from droid_web_display.desktop.platform import StartupManager, install_output_logging

    paths = DesktopPaths.from_resource_root(resource_root)
    install_output_logging(paths.logs_root)

    args, server_args = _desktop_parser().parse_known_args(argv)

    from run_bridge_service import BridgeServiceRuntime, main as bridge_main

    no_desktop = (
        sys.platform.startswith("linux")
        and not os.environ.get("DISPLAY")
        and not os.environ.get("WAYLAND_DISPLAY")
        and not os.environ.get("QT_QPA_PLATFORM")
    )

    if args.desktop_smoke:
        from droid_web_display.desktop.gui import desktop_smoke_test

        return desktop_smoke_test(resource_root / "apps" / "web-client" / "dist" / "favicon.svg")

    if args.headless or no_desktop:
        if no_desktop and not args.headless:
            print("No Linux desktop session detected; starting DroidWebDisplay in headless mode.")
        browser_args = []
        if args.open_browser and not args.no_browser:
            browser_args.append("--open-browser")
        else:
            browser_args.append("--no-browser")
        return bridge_main(paths.server_arguments([*browser_args, *server_args]))

    controller = ServerController(
        paths,
        server_runner=bridge_main,
        runtime_factory=BridgeServiceRuntime,
        server_args=server_args,
    )

    from droid_web_display.desktop.gui import run_desktop_app

    startup = StartupManager(resource_root)
    open_browser = not args.no_browser
    if args.open_browser:
        open_browser = True
    return run_desktop_app(
        controller,
        startup,
        icon_path=resource_root / "apps" / "web-client" / "dist" / "favicon.svg",
        start_minimized=args.start_minimized,
        open_browser=open_browser,
    )


if __name__ == "__main__":
    raise SystemExit(main())
