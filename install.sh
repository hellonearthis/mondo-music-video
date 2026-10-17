#!/usr/bin/env bash
set -euo pipefail
MMV_PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
MMV_PYTHON="${MMV_PYTHON:-python3}"
MMV_NON_INTERACTIVE=false
MMV_INSTALL_STARTERS=true
MMV_STARTER_ARGS=()
for MMV_INSTALL_ARG in "$@"; do
  case "$MMV_INSTALL_ARG" in
    --non-interactive) MMV_NON_INTERACTIVE=true; MMV_STARTER_ARGS+=("--non-interactive") ;;
    --accept-starter-signer) MMV_STARTER_ARGS+=("--accept-starter-signer") ;;
    --skip-starter-assets) MMV_INSTALL_STARTERS=false ;;
    *) echo "Unknown installer option: $MMV_INSTALL_ARG" >&2; exit 1 ;;
  esac
done
"$MMV_PYTHON" -c 'import sys; assert sys.version_info >= (3, 11), "Python 3.11 or newer is required"'
if ! command -v git >/dev/null 2>&1; then
  echo "Install Git first; it is needed for the pinned Open Actor Protocol dependency." >&2
  exit 1
fi
if [ ! -x "$MMV_PROJECT_DIR/.venv/bin/python" ]; then
  "$MMV_PYTHON" -m venv "$MMV_PROJECT_DIR/.venv"
fi
"$MMV_PROJECT_DIR/.venv/bin/python" -m pip install "$MMV_PROJECT_DIR"
if [ "$MMV_INSTALL_STARTERS" = true ]; then
  "$MMV_PROJECT_DIR/.venv/bin/python" -m mmv.setup install-starter-assets "${MMV_STARTER_ARGS[@]}"
fi
if [ "$MMV_NON_INTERACTIVE" = true ]; then
  "$MMV_PROJECT_DIR/.venv/bin/python" -m mmv.setup doctor
else
  "$MMV_PROJECT_DIR/.venv/bin/python" -m mmv.setup configure
fi
echo "Launch: $MMV_PROJECT_DIR/.venv/bin/mondo-music-video serve"
