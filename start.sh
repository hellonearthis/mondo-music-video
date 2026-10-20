#!/usr/bin/env bash
# Start Mondo Music Video on Linux, macOS or Windows through WSL.
#   bash start.sh                 run in this terminal (stop with Ctrl+C)
#   bash start.sh --background    run in the background; stop it with: bash stop.sh
#   bash start.sh --port 8092     any other option is passed to `mondo-music-video serve`
# Data folder: $MMV_HOME if set, else ./data when this checkout already has data there, else the app's default.
set -euo pipefail
MMV_PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
MMV_BIN="$MMV_PROJECT_DIR/.venv/bin/mondo-music-video"
if [ ! -x "$MMV_BIN" ]; then
  echo "Not installed yet: run  bash install.sh  first." >&2
  exit 1
fi
if [ -z "${MMV_HOME:-}" ] && [ -f "$MMV_PROJECT_DIR/data/settings.json" ]; then
  MMV_HOME="$MMV_PROJECT_DIR/data"
fi
MMV_BACKGROUND=false
MMV_PORT=8091
MMV_ARGS=()
while [ "$#" -gt 0 ]; do
  case "$1" in
    --background|-d) MMV_BACKGROUND=true ;;
    --port) MMV_PORT="${2:?--port needs a number}"; shift ;;
    *) MMV_ARGS+=("$1") ;;
  esac
  shift
done
MMV_URL="http://127.0.0.1:$MMV_PORT"
if curl -s -m 2 "$MMV_URL/api/version" 2>/dev/null | grep -q "Mondo Music Video"; then
  echo "Mondo is already running at $MMV_URL (stop it with: bash stop.sh)." >&2
  exit 1
fi
# Run this checkout's code: the .venv may hold an older installed copy of the package.
export PYTHONPATH="$MMV_PROJECT_DIR${PYTHONPATH:+:$PYTHONPATH}"
MMV_DATA=(); [ -n "${MMV_HOME:-}" ] && MMV_DATA=(--data-dir "$MMV_HOME")
MMV_STATE="${MMV_HOME:-${XDG_DATA_HOME:-$HOME/.local/share}/mondo-music-video}"
mkdir -p "$MMV_STATE"
cd "$MMV_PROJECT_DIR"
if [ "$MMV_BACKGROUND" != true ]; then
  echo "Starting Mondo at $MMV_URL  (Ctrl+C to stop)"
  exec "$MMV_BIN" "${MMV_DATA[@]}" serve --port "$MMV_PORT" "${MMV_ARGS[@]}"
fi
nohup "$MMV_BIN" "${MMV_DATA[@]}" serve --port "$MMV_PORT" "${MMV_ARGS[@]}" > "$MMV_STATE/server.log" 2>&1 < /dev/null &
echo $! > "$MMV_STATE/server.pid"
echo "$MMV_URL" > "$MMV_STATE/server-url.txt"
for _ in $(seq 1 40); do
  if curl -s -m 2 "$MMV_URL/api/version" 2>/dev/null | grep -q "Mondo Music Video"; then
    echo "Mondo $(curl -s "$MMV_URL/api/version" | sed 's/.*"version":"\([^"]*\)".*/\1/') is running at $MMV_URL"
    echo "Stop it with: bash stop.sh   (log: $MMV_STATE/server.log)"
    exit 0
  fi
  kill -0 "$(cat "$MMV_STATE/server.pid")" 2>/dev/null || break
  sleep 0.5
done
echo "Mondo did not start; see $MMV_STATE/server.log" >&2
tail -5 "$MMV_STATE/server.log" >&2 || true
exit 1
