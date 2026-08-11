#!/usr/bin/env sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
(cd "$ROOT/packages/scrcpy-protocol" && npm ci --ignore-scripts)
(cd "$ROOT/apps/web-client" && npm ci --ignore-scripts)
echo "Package-local Node.js dependencies installed."
