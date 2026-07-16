#!/usr/bin/env bash
# PiVidSim installer for Raspberry Pi OS Lite (64-bit, Trixie / Debian 13).
#
# Installs dependencies, generates the idle splash, sets the Pi to boot to the
# console, and registers a systemd service that plays USB videos fullscreen via
# DRM/KMS. Idempotent: safe to re-run after a `git pull`.
#
# Usage (from the repo root):
#     sudo bash scripts/install.sh

set -euo pipefail

SERVICE_NAME="pividsim.service"
UNIT_DST="/etc/systemd/system/${SERVICE_NAME}"

# Resolve paths relative to this script so it works from any working directory.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
UNIT_SRC="${REPO_DIR}/systemd/pividsim.service"
GEN_SCRIPT="${REPO_DIR}/scripts/generate-idle.py"

# Re-run under sudo if not already root (needs apt + /etc/systemd/system).
if [[ "${EUID}" -ne 0 ]]; then
    echo "This installer needs root; re-running with sudo..." >&2
    exec sudo -- "$0" "$@"
fi

echo "PiVidSim install"
echo "  repo:    ${REPO_DIR}"
echo "  service: ${UNIT_DST}"
echo

# 1. Dependencies. mpv pulls in the DRM/GL stack; pyudev drives hot-plug;
#    PIL + DejaVu render the idle splash.
echo "==> Installing packages..."
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y mpv python3-pyudev python3-pil fonts-dejavu-core

# 2. Idle splash image (assets/idle.png).
echo "==> Generating idle splash..."
python3 "${GEN_SCRIPT}"

# 3. Boot to the console, not a desktop, so nothing competes for the display.
current_target="$(systemctl get-default || true)"
if [[ "${current_target}" != "multi-user.target" ]]; then
    echo "==> Setting default boot target to console (multi-user.target)..."
    systemctl set-default multi-user.target
fi

# 4. Install, enable, and (re)start the service.
echo "==> Installing systemd unit..."
sed "s|__REPO_DIR__|${REPO_DIR}|g" "${UNIT_SRC}" > "${UNIT_DST}"
chmod 0644 "${UNIT_DST}"

systemctl daemon-reload
systemctl enable "${SERVICE_NAME}"
systemctl restart "${SERVICE_NAME}"

echo
echo "Done — PiVidSim is running and will start on every boot."
echo
echo "  Live logs:  journalctl -u pividsim -f"
echo "  Status:     systemctl status pividsim"
echo "  Stop:       sudo systemctl stop pividsim"
echo
echo "Insert a USB drive containing .mp4 files to start playback."
echo "Reboot once to confirm the boot-time behaviour:  sudo reboot"
