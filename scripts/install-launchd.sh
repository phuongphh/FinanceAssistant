#!/usr/bin/env bash
# Installs the Finance Assistant backend as a launchd service.
# Run once after cloning; re-run to update after template changes.
set -euo pipefail

LABEL="com.financeassistant.backend"
TEMPLATE_DIR="$(cd "$(dirname "$0")/../launchd" && pwd)"
TEMPLATE="$TEMPLATE_DIR/$LABEL.plist.template"
AGENTS_DIR="$HOME/Library/LaunchAgents"
DEST="$AGENTS_DIR/$LABEL.plist"

PROJECT_DIR="${PROJECT_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
PORT="${PORT:-8000}"

if [[ ! -f "$TEMPLATE" ]]; then
    echo "ERROR: template not found at $TEMPLATE" >&2
    exit 1
fi

mkdir -p "$AGENTS_DIR"

sed \
    -e "s|{{PROJECT_DIR}}|$PROJECT_DIR|g" \
    -e "s|{{PORT}}|$PORT|g" \
    "$TEMPLATE" > "$DEST"

echo "Installed: $DEST"
echo "  PROJECT_DIR = $PROJECT_DIR"
echo "  PORT        = $PORT"

# Reload if already loaded
if launchctl list "$LABEL" &>/dev/null; then
    launchctl unload "$DEST"
fi
launchctl load "$DEST"
echo "Loaded: $LABEL"
