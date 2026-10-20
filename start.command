#!/usr/bin/env bash
# Double-click in Finder to start Mondo Music Video in a Terminal window. Close the window or press Ctrl+C to stop it.
cd "$(dirname "$0")" && exec bash start.sh "$@"
