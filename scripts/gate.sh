#!/usr/bin/env sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
exec python "$ROOT/tools/release_gate.py" --output "$ROOT/evidence/release/gate.json" "$@"
