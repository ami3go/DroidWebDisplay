#!/usr/bin/env bash
set -euo pipefail
PARENT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ -f "$PARENT/VERSION.json" ]]; then ROOT="$PARENT"; else ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"; fi
for candidate in "$ROOT/runtime/python/bin/python3" "$ROOT/runtime/python/python3" "$ROOT/.venv/bin/python3" "$ROOT/.venv/bin/python"; do
  if [[ -x "$candidate" ]]; then PYTHON="$candidate"; break; fi
done
: "${PYTHON:?Gpt-Bridge Python runtime not found. Run install.sh first.}"
exec "$PYTHON" "$ROOT/tools/run_bridge_service.py" --repo-root "$ROOT" --pid-file "$ROOT/data/service.pid" --open-browser "$@"
