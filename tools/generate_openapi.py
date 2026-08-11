#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import fastapi
import pydantic
import starlette

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from droid_web_display.api import create_app
from droid_web_display.config import BridgeConfig


def render(repo_root: Path) -> str:
    app = create_app(config=BridgeConfig(repo_root=repo_root, adb_executable="adb"))
    return json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate or verify the DroidWebDisplay OpenAPI document")
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    root = args.repo_root.resolve()
    output = args.output or root / "packages" / "bridge-api" / "openapi" / "openapi-v1.json"
    generated = render(root)
    if args.check:
        if not output.is_file() or output.read_text(encoding="utf-8") != generated:
            print(f"OpenAPI document is out of date: {output}")
            print(
                "Generator versions: "
                f"fastapi={fastapi.__version__}, "
                f"pydantic={pydantic.__version__}, "
                f"starlette={starlette.__version__}"
            )
            print('Install the canonical environment with: python -m pip install --upgrade --force-reinstall -e ".[dev]"')
            return 1
        print(f"OpenAPI document is current: {output}")
        return 0

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(generated, encoding="utf-8")
    print(f"Wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
