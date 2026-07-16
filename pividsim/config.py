"""Static configuration for PiVidSim.

All tunables live here so the rest of the package stays declarative. A few
values can be overridden at runtime through environment variables (see the
systemd unit) without editing code.
"""
from __future__ import annotations

import os
from pathlib import Path

# --- Paths ------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = REPO_ROOT / "assets"
IDLE_IMAGE = ASSETS_DIR / "idle.png"

# PiVidSim mounts USB partitions itself, because Raspberry Pi OS Lite has no
# desktop auto-mounter (udisks/PCManFM). We own everything under this dir.
MOUNT_ROOT = Path(os.environ.get("PIVIDSIM_MOUNT_ROOT", "/run/pividsim/mounts"))

# Filesystem types we are willing to mount from removable drives.
USB_FS_TYPES = frozenset({"vfat", "exfat", "ntfs", "ext4", "ext3", "ext2"})

# Mount options: read-only so an unclean unplug can never corrupt the stick,
# plus the usual hardening for untrusted removable media.
MOUNT_OPTIONS = "ro,nosuid,nodev,noexec"

# --- Video enumeration ------------------------------------------------------

VIDEO_EXTENSIONS = frozenset({".mp4", ".m4v", ".mov", ".mkv"})

# --- Timing (seconds) -------------------------------------------------------

SETTLE_SECONDS = 2.0        # grace after a udev event before scanning mounts
WATCHDOG_INTERVAL = 5.0     # main-loop poll cadence for mpv liveness
STOP_TIMEOUT = 3.0          # SIGTERM -> SIGKILL grace when stopping mpv
MOUNT_TIMEOUT = 15.0        # max seconds to wait for a mount/umount command

# --- mpv invocations --------------------------------------------------------
#
# We render straight to the display controller via DRM/KMS — no X11, no
# Wayland, no desktop. Two knobs are exposed as env vars so the picture and
# hardware decoding can be tuned on-device without editing code:
#
#   PIVIDSIM_MPV_VO    video output driver:
#                        "drm"  (default) — direct KMS, fewest dependencies
#                        "gpu"           — GPU-scaled (adds --gpu-context=drm)
#   PIVIDSIM_MPV_HWDEC hardware decoder:
#                        "v4l2m2m-copy" (default) — Pi H.264 HW decode
#                        "auto-safe"              — let mpv choose
#                        "no"                     — force software decode

MPV_VO = os.environ.get("PIVIDSIM_MPV_VO", "drm")
MPV_HWDEC = os.environ.get("PIVIDSIM_MPV_HWDEC", "v4l2m2m-copy")

_VO_ARGS: list[str] = [f"--vo={MPV_VO}"]
if MPV_VO == "gpu":
    # GPU output needs an EGL/GBM context; on a console that means DRM.
    _VO_ARGS.append("--gpu-context=drm")

MPV_COMMON: list[str] = [
    "mpv",
    *_VO_ARGS,
    "--fullscreen",
    "--no-osc",                     # no on-screen controller
    "--no-input-default-bindings",  # ignore keyboard
    "--no-terminal",                # we run headless under systemd
    "--really-quiet",
    "--msg-level=all=warn",         # surface real problems in the journal
]

MPV_PLAY_ARGS: list[str] = MPV_COMMON + [
    "--loop-playlist=inf",
    f"--hwdec={MPV_HWDEC}",
    "--audio-device=auto",
]

MPV_IDLE_ARGS: list[str] = MPV_COMMON + [
    "--image-display-duration=inf",
    "--loop-file=inf",
    "--no-audio",
]
