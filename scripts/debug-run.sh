#!/usr/bin/env bash
# Run PiVidSim in the foreground for debugging.
#
# Stops the background service first (so two mpv instances don't fight over the
# DRM display), then runs the app as root — required to mount USB drives and to
# open /dev/dri directly. Press Ctrl-C to stop, then resume normal operation
# with:  sudo systemctl start pividsim
#
# Usage:  bash scripts/debug-run.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

if [[ "${EUID}" -ne 0 ]]; then
    exec sudo -- "$0" "$@"
fi

echo "Stopping pividsim.service (if running)..."
systemctl stop pividsim.service 2>/dev/null || true

cd "${REPO_DIR}"
echo "Running pividsim in the foreground (Ctrl-C to stop)..."
exec python3 -m pividsim.main
