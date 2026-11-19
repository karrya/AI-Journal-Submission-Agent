#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOMAIN="gui/$(id -u)"
BACKEND_LABEL="com.academic-submission-agent.backend"
WORKER_LABEL="com.academic-submission-agent.worker"
BACKEND_PLIST="$HOME/Library/LaunchAgents/${BACKEND_LABEL}.plist"
WORKER_PLIST="$HOME/Library/LaunchAgents/${WORKER_LABEL}.plist"
ACTION="${1:-start}"

create_plists() {
    mkdir -p "$HOME/Library/LaunchAgents" "$ROOT_DIR/storage/logs"
    ROOT_DIR="$ROOT_DIR" "$ROOT_DIR/.venv/bin/python" - <<'PY'
import os
import plistlib
from pathlib import Path

root = Path(os.environ["ROOT_DIR"])
launch_agents = Path.home() / "Library" / "LaunchAgents"
services = {
    "backend": root / "scripts" / "dev_backend.sh",
    "worker": root / "scripts" / "dev_worker.sh",
}
for name, script in services.items():
    label = f"com.academic-submission-agent.{name}"
    log_root = root / "storage" / "logs"
    payload = {
        "Label": label,
        "ProgramArguments": ["/bin/bash", str(script)],
        "WorkingDirectory": str(root),
        "RunAtLoad": True,
        "KeepAlive": True,
        "ThrottleInterval": 5,
        "ProcessType": "Background",
        "EnvironmentVariables": {"PYTHONUNBUFFERED": "1"},
        "StandardOutPath": str(log_root / f"{name}.out.log"),
        "StandardErrorPath": str(log_root / f"{name}.error.log"),
    }
    destination = launch_agents / f"{label}.plist"
    temporary = destination.with_suffix(".tmp")
    temporary.write_bytes(plistlib.dumps(payload, sort_keys=False))
    temporary.replace(destination)
PY
}

stop_duplicate_backend() {
    local listener_pid service_pid command
    listener_pid=$(lsof -tiTCP:8000 -sTCP:LISTEN || true)
    [[ -z "$listener_pid" ]] && return 0
    service_pid=$(launchctl print "$DOMAIN/$BACKEND_LABEL" 2>/dev/null | awk '/pid =/{print $3}' || true)
    [[ "$listener_pid" == "$service_pid" ]] && return 0
    command=$(ps -p "$listener_pid" -o command=)
    case "$command" in
        *app.main:app*)
            kill "$listener_pid"
            sleep 2
            ;;
        *)
            printf '8000 端口被非本应用进程占用：%s\n' "$command" >&2
            return 1
            ;;
    esac
}

start_services() {
    stop_duplicate_backend
    create_plists
    for item in "$BACKEND_LABEL:$BACKEND_PLIST" "$WORKER_LABEL:$WORKER_PLIST"; do
        label="${item%%:*}"
        plist="${item#*:}"
        if launchctl print "$DOMAIN/$label" >/dev/null 2>&1; then
            if [[ "$ACTION" == "restart" ]]; then
                launchctl kickstart -k "$DOMAIN/$label"
            fi
            continue
        fi
        attempt=0
        until launchctl bootstrap "$DOMAIN" "$plist"; do
            attempt=$((attempt + 1))
            if (( attempt >= 5 )); then
                printf '服务注册失败：%s；请检查 plist 和当前用户 launchd 状态，不要使用 root。\n' "$label" >&2
                return 1
            fi
            sleep 2
        done
        launchctl kickstart -k "$DOMAIN/$label"
    done
}

stop_services() {
    for label in "$BACKEND_LABEL" "$WORKER_LABEL"; do
        launchctl bootout "$DOMAIN/$label" 2>/dev/null || true
    done
}

status_services() {
    for label in "$BACKEND_LABEL" "$WORKER_LABEL"; do
        printf '\n=== %s ===\n' "$label"
        launchctl print "$DOMAIN/$label" 2>/dev/null || printf '未安装或未运行\n'
    done
}

case "${1:-start}" in
    restart)
        stop_services
        start_services
        ;;
    start|install)
        start_services
        ;;
    stop)
        stop_services
        ;;
    status)
        status_services
        ;;
    uninstall)
        stop_services
        rm -f "$BACKEND_PLIST" "$WORKER_PLIST"
        ;;
    *)
        printf '用法：%s [start|install|restart|stop|status|uninstall]\n' "$0" >&2
        exit 2
        ;;
esac
