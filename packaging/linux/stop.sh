#!/usr/bin/env bash
set -euo pipefail
PARENT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ -f "$PARENT/VERSION.json" ]]; then ROOT="$PARENT"; else ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"; fi
for candidate in "$ROOT/runtime/python/bin/python3" "$ROOT/runtime/python/python3" "$ROOT/.venv/bin/python3" "$ROOT/.venv/bin/python"; do
  if [[ -x "$candidate" ]]; then PYTHON="$candidate"; break; fi
done
: "${PYTHON:?Installed Python runtime not found.}"
exec "$PYTHON" "$ROOT/tools/stop_bridge_service.py" --pid-file "$ROOT/data/service.pid" "$@"
