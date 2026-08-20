#!/usr/bin/env bash
set -euo pipefail
PARENT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ -f "$PARENT/VERSION.json" ]]; then SOURCE="$PARENT"; else SOURCE="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"; fi
INSTALL_ROOT="${DROID_WEB_DISPLAY_INSTALL_ROOT:-$HOME/.local/share/droidwebdisplay}"
BIN_DIR="${XDG_BIN_HOME:-$HOME/.local/bin}"
SYSTEMD_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
DESKTOP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
ICON_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/scalable/apps"

SOURCE_REAL="$(cd "$SOURCE" && pwd)"
mkdir -p "$INSTALL_ROOT"
INSTALL_REAL="$(cd "$INSTALL_ROOT" && pwd)"
if [[ "$SOURCE_REAL" == "$INSTALL_REAL" ]]; then
  echo "ERROR: install root must differ from release source." >&2
  exit 2
fi

systemctl --user stop droidwebdisplay.service >/dev/null 2>&1 || true
for candidate in "$INSTALL_ROOT/runtime/python/bin/python3" "$INSTALL_ROOT/runtime/python/python3" "$INSTALL_ROOT/.venv/bin/python3" "$INSTALL_ROOT/.venv/bin/python"; do
  if [[ -x "$candidate" && -f "$INSTALL_ROOT/tools/stop_bridge_service.py" ]]; then
    "$candidate" "$INSTALL_ROOT/tools/stop_bridge_service.py" --pid-file "$INSTALL_ROOT/data/service.pid" >/dev/null 2>&1 || true
    break
  fi
done

mkdir -p "$INSTALL_ROOT" "$BIN_DIR" "$SYSTEMD_DIR" "$DESKTOP_DIR" "$ICON_DIR"
for state in data downloads logs; do mkdir -p "$INSTALL_ROOT/$state"; done

# Refresh executable application files while preserving runtime state and any
# installed virtual environment. Python stdlib copying avoids an rsync dependency.
SOURCE="$SOURCE" INSTALL_ROOT="$INSTALL_ROOT" python3 - <<'PY'
from pathlib import Path
import os, shutil
src = Path(os.environ["SOURCE"]).resolve()
dst = Path(os.environ["INSTALL_ROOT"]).resolve()
preserve = {"data", "downloads", "logs", ".venv"}
ignore = {"evidence", "node_modules", ".pytest_cache", "__pycache__", ".git"}
for child in list(dst.iterdir()):
    if child.name in preserve:
        continue
    if child.is_dir() and not child.is_symlink():
        shutil.rmtree(child)
    else:
        child.unlink(missing_ok=True)
for child in src.iterdir():
    if child.name in preserve or child.name in ignore:
        continue
    target = dst / child.name
    if child.is_dir():
        shutil.copytree(child, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache", "node_modules", ".git"))
    elif child.is_file():
        shutil.copy2(child, target)
PY

RUNTIME=""
for candidate in "$INSTALL_ROOT/runtime/python/bin/python3" "$INSTALL_ROOT/runtime/python/python3"; do
  if [[ -x "$candidate" ]]; then RUNTIME="$candidate"; break; fi
done
if [[ -z "$RUNTIME" ]]; then
  HOST_PYTHON="${PYTHON:-$(command -v python3 || true)}"
  if [[ -z "$HOST_PYTHON" ]]; then echo "ERROR: Python 3.11+ is required unless a bundled runtime is included." >&2; exit 2; fi
  "$HOST_PYTHON" - <<'PY'
import sys
if sys.version_info < (3, 11): raise SystemExit("Python 3.11 or newer is required")
PY
  if [[ ! -x "$INSTALL_ROOT/.venv/bin/python3" && ! -x "$INSTALL_ROOT/.venv/bin/python" ]]; then
    "$HOST_PYTHON" -m venv "$INSTALL_ROOT/.venv"
  fi
  if [[ -x "$INSTALL_ROOT/.venv/bin/python3" ]]; then RUNTIME="$INSTALL_ROOT/.venv/bin/python3"; else RUNTIME="$INSTALL_ROOT/.venv/bin/python"; fi
  if [[ -d "$INSTALL_ROOT/wheelhouse" ]] && compgen -G "$INSTALL_ROOT/wheelhouse/*" >/dev/null; then
    "$RUNTIME" -m pip install --disable-pip-version-check --no-index --find-links "$INSTALL_ROOT/wheelhouse" -e "$INSTALL_ROOT"
  elif [[ "${DROID_WEB_DISPLAY_ALLOW_ONLINE_DEPENDENCIES:-0}" == "1" ]]; then
    "$RUNTIME" -m pip install --disable-pip-version-check -e "$INSTALL_ROOT"
  else
    echo "ERROR: offline wheelhouse is not present." >&2
    echo "Use a complete offline release or set DROID_WEB_DISPLAY_ALLOW_ONLINE_DEPENDENCIES=1 on an Internet-connected machine." >&2
    exit 2
  fi
fi

cat > "$BIN_DIR/droidwebdisplay" <<EOF2
#!/usr/bin/env bash
exec "$INSTALL_ROOT/DroidWebDisplay.sh" "\$@"
EOF2
chmod +x "$BIN_DIR/droidwebdisplay"
cat > "$BIN_DIR/droidwebdisplay-stop" <<EOF2
#!/usr/bin/env bash
for candidate in "$INSTALL_ROOT/runtime/python/bin/python3" "$INSTALL_ROOT/runtime/python/python3" "$INSTALL_ROOT/.venv/bin/python3" "$INSTALL_ROOT/.venv/bin/python"; do
  if [[ -x "\$candidate" ]]; then exec "\$candidate" "$INSTALL_ROOT/tools/stop_bridge_service.py" --pid-file "$INSTALL_ROOT/data/service.pid" "\$@"; fi
done
echo "Installed Python runtime not found." >&2
exit 2
EOF2
chmod +x "$BIN_DIR/droidwebdisplay-stop"

sed "s|@INSTALL_ROOT@|$INSTALL_ROOT|g" "$INSTALL_ROOT/packaging/linux/droidwebdisplay.service.in" > "$SYSTEMD_DIR/droidwebdisplay.service"
sed "s|@LAUNCHER@|$BIN_DIR/droidwebdisplay|g" "$INSTALL_ROOT/packaging/linux/droidwebdisplay.desktop.in" > "$DESKTOP_DIR/droidwebdisplay.desktop"
# The desktop entry names Icon=droidwebdisplay, so the SVG has to be on the
# icon search path or the launcher shows a generic placeholder. The AppImage
# ships its own copy; a system install had none.
install -m 0644 "$INSTALL_ROOT/packaging/linux/droidwebdisplay.svg" "$ICON_DIR/droidwebdisplay.svg"
gtk-update-icon-cache -f -t "${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor" >/dev/null 2>&1 || true
systemctl --user daemon-reload >/dev/null 2>&1 || true
printf 'Installed DroidWebDisplay to %s\n' "$INSTALL_ROOT"
printf 'Start now: systemctl --user start droidwebdisplay.service\n'
printf 'Enable at login: systemctl --user enable droidwebdisplay.service\n'
