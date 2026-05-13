#!/usr/bin/env bash
# Install Cloudflare Tunnel as a macOS LaunchAgent so it auto-starts on login.
# Run AFTER tunnel-named-setup.sh succeeds.
#
# Manages two agents:
#   com.financeassistant.tunnel  — named tunnel (stable URL)
#   com.financeassistant.backend — FastAPI backend on port 8000
#
# Usage:
#   ./scripts/launchagent-install.sh install   # install & start
#   ./scripts/launchagent-install.sh uninstall # stop & remove
#   ./scripts/launchagent-install.sh status    # show status

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LAUNCH_AGENTS_DIR="${HOME}/Library/LaunchAgents"
LOGS_DIR="${HOME}/Library/Logs/finance-assistant"

TUNNEL_PLIST="${LAUNCH_AGENTS_DIR}/com.financeassistant.tunnel.plist"
BACKEND_PLIST="${LAUNCH_AGENTS_DIR}/com.financeassistant.backend.plist"

ACTION="${1:-install}"

mkdir -p "$LAUNCH_AGENTS_DIR" "$LOGS_DIR"

# ── Tunnel LaunchAgent ─────────────────────────────────────────────────────────
write_tunnel_plist() {
    local CONFIG_FILE="${PROJECT_ROOT}/.cloudflared/config.yml"
    if [[ ! -f "$CONFIG_FILE" ]]; then
        echo "Warning: ${CONFIG_FILE} not found. Run tunnel-named-setup.sh first."
        echo "Skipping tunnel LaunchAgent."
        return 0
    fi

    cat > "$TUNNEL_PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
    "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.financeassistant.tunnel</string>

    <key>ProgramArguments</key>
    <array>
        <string>/opt/homebrew/bin/cloudflared</string>
        <string>tunnel</string>
        <string>--config</string>
        <string>${CONFIG_FILE}</string>
        <string>run</string>
    </array>

    <key>RunAtLoad</key>
    <true/>

    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key>
        <false/>
    </dict>

    <key>StandardOutPath</key>
    <string>${LOGS_DIR}/tunnel.log</string>

    <key>StandardErrorPath</key>
    <string>${LOGS_DIR}/tunnel.log</string>

    <key>ThrottleInterval</key>
    <integer>10</integer>
</dict>
</plist>
EOF
    echo "  Written: $TUNNEL_PLIST"
}

# ── Backend LaunchAgent ────────────────────────────────────────────────────────
write_backend_plist() {
    local VENV_PYTHON="${PROJECT_ROOT}/venv/bin/python"
    local BACKEND_DIR="${PROJECT_ROOT}/backend"
    local PORT="${FINANCE_BACKEND_PORT:-8000}"

    cat > "$BACKEND_PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
    "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.financeassistant.backend</string>

    <key>ProgramArguments</key>
    <array>
        <string>${VENV_PYTHON}</string>
        <string>-m</string>
        <string>uvicorn</string>
        <string>main:app</string>
        <string>--host</string>
        <string>0.0.0.0</string>
        <string>--port</string>
        <string>${PORT}</string>
    </array>

    <key>WorkingDirectory</key>
    <string>${BACKEND_DIR}</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
    </dict>

    <key>RunAtLoad</key>
    <true/>

    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key>
        <false/>
    </dict>

    <key>StandardOutPath</key>
    <string>${LOGS_DIR}/backend.log</string>

    <key>StandardErrorPath</key>
    <string>${LOGS_DIR}/backend.log</string>

    <key>ThrottleInterval</key>
    <integer>10</integer>
</dict>
</plist>
EOF
    echo "  Written: $BACKEND_PLIST"
}

case "$ACTION" in
install)
    echo "Installing LaunchAgents..."
    write_backend_plist
    write_tunnel_plist

    for plist in "$BACKEND_PLIST" "$TUNNEL_PLIST"; do
        [[ -f "$plist" ]] || continue
        label=$(basename "$plist" .plist)
        launchctl unload "$plist" 2>/dev/null || true
        launchctl load "$plist"
        echo "  Loaded: $label"
    done

    echo ""
    echo "LaunchAgents installed. They will auto-start on login."
    echo "Logs: $LOGS_DIR/"
    ;;

uninstall)
    echo "Removing LaunchAgents..."
    for plist in "$BACKEND_PLIST" "$TUNNEL_PLIST"; do
        [[ -f "$plist" ]] || continue
        label=$(basename "$plist" .plist)
        launchctl unload "$plist" 2>/dev/null && echo "  Unloaded: $label"
        rm -f "$plist" && echo "  Removed: $plist"
    done
    ;;

status)
    echo "LaunchAgent status:"
    for label in com.financeassistant.backend com.financeassistant.tunnel; do
        status=$(launchctl list "$label" 2>/dev/null | grep '"PID"' | awk '{print $3}' | tr -d ';' || echo "")
        if [[ -n "$status" && "$status" != "0" ]]; then
            echo "  $label: RUNNING (PID $status)"
        else
            exit_code=$(launchctl list "$label" 2>/dev/null | grep '"LastExitStatus"' | awk '{print $3}' | tr -d ';' || echo "")
            if [[ -n "$exit_code" ]]; then
                echo "  $label: STOPPED (last exit: $exit_code)"
            else
                echo "  $label: NOT LOADED"
            fi
        fi
    done
    ;;

*)
    echo "Usage: $0 [install|uninstall|status]"
    exit 1
    ;;
esac
