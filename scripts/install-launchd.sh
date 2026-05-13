#!/usr/bin/env bash
# Installs Finance Assistant backend + scheduler as launchd services.
# Run once after cloning; re-run to update after template changes.
#
# Optional env vars:
#   PROJECT_DIR  — defaults to the repo root (parent of this script)
#   PORT         — uvicorn port (default: 8000)
set -euo pipefail

TEMPLATE_DIR="$(cd "$(dirname "$0")/../launchd" && pwd)"
AGENTS_DIR="$HOME/Library/LaunchAgents"

PROJECT_DIR="${PROJECT_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
PORT="${PORT:-8000}"

mkdir -p "$AGENTS_DIR"

install_service() {
    local label="$1"
    local template="$TEMPLATE_DIR/$label.plist.template"
    local dest="$AGENTS_DIR/$label.plist"

    if [[ ! -f "$template" ]]; then
        echo "ERROR: template not found at $template" >&2
        return 1
    fi

    sed \
        -e "s|{{PROJECT_DIR}}|$PROJECT_DIR|g" \
        -e "s|{{PORT}}|$PORT|g" \
        "$template" > "$dest"

    echo "Installed: $dest"

    if launchctl list "$label" &>/dev/null; then
        launchctl unload "$dest"
    fi
    launchctl load "$dest"
    echo "Loaded:    $label"
}

echo "PROJECT_DIR = $PROJECT_DIR"
echo "PORT        = $PORT"
echo ""

install_service "com.financeassistant.backend"
install_service "com.financeassistant.scheduler"

echo ""
echo "Both services are running. Check status with:"
echo "  launchctl list | grep financeassistant"
