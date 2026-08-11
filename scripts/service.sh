#!/usr/bin/env sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
exec python "$ROOT/tools/run_bridge_service.py" --repo-root "$ROOT" --open-browser "$@"
