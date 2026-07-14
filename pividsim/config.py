"""Static configuration for PiVidSim.

All tunables live here so the rest of the package stays declarative.
"""
from __future__ import annotations

import getpass
from pathlib import Path

# --- Paths ------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = REPO_ROOT / "assets"
IDLE_IMAGE = ASSETS_DIR / "idle.png"

# udisks2 on Raspberry Pi OS Desktop mounts removable drives under
# /media/<current-user>/<label-or-uuid>. Fall back to "pi" if USER is missing
# (e.g. very early in a service context).
try:
    _USER = getpass.getuser()
except Exception:  # noqa: BLE001
    _USER = "pi"
MOUNT_ROOT = Path("/media") / _USER

# Filesystem types considered candidates for USB storage.
USB_FS_TYPES = frozenset({"vfat", "exfat", "ntfs", "ext4", "ext3", "ext2"})

# --- Video enumeration ------------------------------------------------------

# H.264-only per spec. Broaden later if HEVC/etc. is ever supported in HW.
VIDEO_EXTENSIONS = frozenset({".mp4", ".m4v", ".mov"})

# --- Timing (seconds) -------------------------------------------------------

SETTLE_SECONDS = 2.0        # grace after a udev event before scanning mounts
WATCHDOG_INTERVAL = 5.0     # main-loop poll cadence for mpv liveness
STOP_TIMEOUT = 3.0          # SIGTERM -> SIGKILL grace when stopping mpv

# --- mpv invocations --------------------------------------------------------

MPV_COMMON: list[str] = [
    "mpv",
    "--fullscreen",
    "--vo=gpu",
    "--force-window=yes",
    "--no-osc",
    "--no-input-default-bindings",
    "--really-quiet",
    "--no-terminal",
]

MPV_PLAY_ARGS: list[str] = MPV_COMMON + [
    "--loop-playlist=inf",
    "--hwdec=v4l2m2m",
    "--audio-device=auto",
]

MPV_IDLE_ARGS: list[str] = MPV_COMMON + [
    "--image-display-duration=inf",
    "--loop-file=inf",
    "--no-audio",
]
