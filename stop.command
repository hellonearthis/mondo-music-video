#!/usr/bin/env bash
# Double-click in Finder to stop a Mondo Music Video that was started in the background (bash start.sh --background).
cd "$(dirname "$0")" && bash stop.sh "$@"
status=$?
read -r -p "Press Return to close this window." _
exit $status
