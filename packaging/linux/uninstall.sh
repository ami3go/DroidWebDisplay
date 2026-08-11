#!/usr/bin/env bash
set -euo pipefail
INSTALL_ROOT="${GPT_BRIDGE_INSTALL_ROOT:-$HOME/.local/share/gpt-bridge}"
BIN_DIR="${XDG_BIN_HOME:-$HOME/.local/bin}"
SYSTEMD_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
DESKTOP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
PURGE=0
[[ "${1:-}" == "--purge-data" ]] && PURGE=1
systemctl --user disable --now gpt-bridge.service >/dev/null 2>&1 || true
rm -f "$SYSTEMD_DIR/gpt-bridge.service" "$BIN_DIR/gpt-bridge" "$BIN_DIR/gpt-bridge-stop" "$DESKTOP_DIR/gpt-bridge.desktop"
systemctl --user daemon-reload >/dev/null 2>&1 || true
if [[ $PURGE -eq 1 ]]; then
  rm -rf "$INSTALL_ROOT"
  echo "Application and runtime data removed."
  exit 0
fi
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
for state in data downloads logs; do
  [[ -d "$INSTALL_ROOT/$state" ]] && mv "$INSTALL_ROOT/$state" "$TMP/$state"
done
rm -rf "$INSTALL_ROOT"
mkdir -p "$INSTALL_ROOT"
for state in data downloads logs; do
  [[ -d "$TMP/$state" ]] && mv "$TMP/$state" "$INSTALL_ROOT/$state"
done
echo "Application removed; runtime state preserved in $INSTALL_ROOT. Use --purge-data to remove it."
