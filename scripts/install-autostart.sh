#!/bin/bash
# Idempotent installer:
#   1. Generate the idle splash PNG if missing.
#   2. Ensure run.sh is executable.
#   3. Wire pividsim into ~/.config/labwc/autostart (only once).

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
RUN_SCRIPT="${REPO_DIR}/scripts/run.sh"
IDLE_IMAGE="${REPO_DIR}/assets/idle.png"
GEN_SCRIPT="${REPO_DIR}/scripts/generate-idle.py"
AUTOSTART_DIR="${HOME}/.config/labwc"
AUTOSTART_FILE="${AUTOSTART_DIR}/autostart"
MARKER="# pividsim-autostart"

echo "PiVidSim install: repo=${REPO_DIR}"

# 1. Generate idle splash if missing.
if [[ ! -f "${IDLE_IMAGE}" ]]; then
    echo "Generating idle splash image..."
    python3 "${GEN_SCRIPT}"
else
    echo "Idle splash already present: ${IDLE_IMAGE}"
fi

# 2. Ensure run.sh is executable.
chmod +x "${RUN_SCRIPT}"

# 3. Wire labwc autostart.
mkdir -p "${AUTOSTART_DIR}"
touch "${AUTOSTART_FILE}"

if grep -Fq "${MARKER}" "${AUTOSTART_FILE}"; then
    echo "labwc autostart entry already present in ${AUTOSTART_FILE}"
else
    {
        echo ""
        echo "${MARKER}"
        echo "\"${RUN_SCRIPT}\" &"
    } >> "${AUTOSTART_FILE}"
    echo "Added pividsim autostart entry to ${AUTOSTART_FILE}"
fi

echo ""
echo "Install complete. Reboot to start pividsim on next login:"
echo "    sudo reboot"
