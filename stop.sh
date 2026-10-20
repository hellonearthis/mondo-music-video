#!/usr/bin/env bash
# Stop a Mondo Music Video started with: bash start.sh --background
# Refuses while a production is running unless you pass --force (cancel it in the app first if you can).
set -euo pipefail
MMV_PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [ -z "${MMV_HOME:-}" ] && [ -f "$MMV_PROJECT_DIR/data/settings.json" ]; then
  MMV_HOME="$MMV_PROJECT_DIR/data"
fi
if [ "$(uname -s)" = "Darwin" ]; then MMV_DEFAULT_HOME="$HOME/Library/Application Support/mondo-music-video"
else MMV_DEFAULT_HOME="${XDG_DATA_HOME:-$HOME/.local/share}/mondo-music-video"; fi      # where the app keeps its data by default
MMV_STATE="${MMV_HOME:-$MMV_DEFAULT_HOME}"
MMV_PIDFILE="$MMV_STATE/server.pid"
if [ ! -f "$MMV_PIDFILE" ]; then
  echo "No server.pid in $MMV_STATE. If Mondo is running in a terminal, press Ctrl+C there." >&2
  exit 1
fi
MMV_PID="$(cat "$MMV_PIDFILE")"
if ! kill -0 "$MMV_PID" 2>/dev/null || ! ps -p "$MMV_PID" -o command= 2>/dev/null | grep -q "mondo-music-video"; then
  echo "Mondo is not running (the recorded process $MMV_PID is gone)."
  rm -f "$MMV_PIDFILE"
  exit 0
fi
MMV_URL="$(cat "$MMV_STATE/server-url.txt" 2>/dev/null || echo http://127.0.0.1:8091)"
if [ "${1:-}" != "--force" ] && curl -s -m 3 "$MMV_URL/api/status" 2>/dev/null | grep -q '"state":"running"'; then
  echo "A production is running. Cancel it in the app first, or run: bash stop.sh --force" >&2
  exit 1
fi
kill -TERM "$MMV_PID"
for _ in $(seq 1 30); do
  kill -0 "$MMV_PID" 2>/dev/null || { rm -f "$MMV_PIDFILE"; echo "Mondo stopped."; exit 0; }
  sleep 0.5
done
echo "Mondo is still shutting down (process $MMV_PID); run bash stop.sh again in a moment." >&2
exit 1
