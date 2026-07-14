#!/bin/bash
# PiVidSim launcher — keeps the app alive with a simple retry loop.
# Invoked by ~/.config/labwc/autostart at graphical login.

set -u

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOG_FILE="${REPO_DIR}/pividsim.log"

cd "${REPO_DIR}"

while true; do
    echo "[run.sh] $(date -Is) starting pividsim" >> "${LOG_FILE}"
    python3 -m pividsim.main >> "${LOG_FILE}" 2>&1
    rc=$?
    echo "[run.sh] $(date -Is) pividsim exited rc=${rc}" >> "${LOG_FILE}"
    # If we were signalled cleanly, bail out (labwc is likely shutting down).
    if [[ ${rc} -eq 0 || ${rc} -eq 143 || ${rc} -eq 130 ]]; then
        exit ${rc}
    fi
    sleep 3
done
