"""USB discovery, self-mounting, and udev-based hot-plug monitoring.

On Raspberry Pi OS Lite there is no desktop file manager to auto-mount
removable drives, so PiVidSim mounts them itself (read-only) under
``MOUNT_ROOT``. A background udev thread reports plug/unplug events; the main
loop then calls :meth:`MountManager.sync` to reconcile mounts on demand.
"""
from __future__ import annotations

import logging
import queue
import subprocess
import threading
from pathlib import Path
from typing import Iterator

import pyudev

from .config import (
    MOUNT_OPTIONS,
    MOUNT_ROOT,
    MOUNT_TIMEOUT,
    USB_FS_TYPES,
    VIDEO_EXTENSIONS,
)

log = logging.getLogger(__name__)


def iter_usb_partitions() -> Iterator[tuple[str, str]]:
    """Yield ``(device_node, fstype)`` for every mountable USB partition.

    Filters to genuine USB block partitions carrying a filesystem we support,
    which naturally excludes the Pi's SD card (``mmcblk*``, bus ``mmc``).
    """
    context = pyudev.Context()
    for dev in context.list_devices(subsystem="block", DEVTYPE="partition"):
        if dev.get("ID_BUS") != "usb":
            continue
        fstype = dev.get("ID_FS_TYPE")
        node = dev.device_node
        if not node or fstype not in USB_FS_TYPES:
            continue
        yield node, fstype


class MountManager:
    """Owns read-only mounts of USB partitions under ``MOUNT_ROOT``.

    :meth:`sync` is idempotent: it mounts partitions that appeared and unmounts
    those that vanished, returning the set of currently mounted paths. This
    matches the "rescan on any event" philosophy of the main loop.
    """

    def __init__(self) -> None:
        # device_node -> mountpoint
        self._mounts: dict[str, Path] = {}

    def sync(self) -> list[Path]:
        """Reconcile mounts with the set of present USB partitions."""
        present = dict(iter_usb_partitions())  # node -> fstype

        # Unmount anything that disappeared.
        for node in list(self._mounts):
            if node not in present:
                self._unmount(node)

        # Mount anything new.
        for node, fstype in present.items():
            if node not in self._mounts:
                self._mount(node, fstype)

        return list(self._mounts.values())

    def unmount_all(self) -> None:
        """Tear down every mount we created (used on shutdown)."""
        for node in list(self._mounts):
            self._unmount(node)

    # --- Internals ----------------------------------------------------------

    def _mount(self, node: str, fstype: str) -> None:
        # Derive a stable, filesystem-safe mountpoint name from the node.
        name = node.replace("/", "_").lstrip("_")
        mountpoint = MOUNT_ROOT / name
        try:
            mountpoint.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            log.error("Cannot create mountpoint %s: %s", mountpoint, exc)
            return

        cmd = [
            "mount",
            "-t", fstype,
            "-o", MOUNT_OPTIONS,
            node, str(mountpoint),
        ]
        try:
            subprocess.run(
                cmd, check=True, capture_output=True, text=True,
                timeout=MOUNT_TIMEOUT,
            )
        except FileNotFoundError:
            log.error("'mount' not found; cannot mount %s", node)
            return
        except subprocess.TimeoutExpired:
            log.error("Timed out mounting %s", node)
            return
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or "").strip()
            log.error("Failed to mount %s (%s): %s", node, fstype, stderr)
            self._rmdir(mountpoint)
            return

        self._mounts[node] = mountpoint
        log.info("Mounted %s (%s, ro) at %s", node, fstype, mountpoint)

    def _unmount(self, node: str) -> None:
        mountpoint = self._mounts.pop(node, None)
        if mountpoint is None:
            return
        # Lazy unmount: the device may already be physically gone.
        try:
            subprocess.run(
                ["umount", "-l", str(mountpoint)],
                check=False, capture_output=True, text=True,
                timeout=MOUNT_TIMEOUT,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            log.warning("Error unmounting %s: %s", mountpoint, exc)
        else:
            log.info("Unmounted %s (%s)", mountpoint, node)
        self._rmdir(mountpoint)

    @staticmethod
    def _rmdir(mountpoint: Path) -> None:
        try:
            mountpoint.rmdir()
        except OSError:
            # Non-empty (still mounted) or already gone — leave it be.
            pass


def list_videos(mount: Path) -> list[Path]:
    """Return a sorted list of video files (by extension) under `mount`."""
    if not mount.is_dir():
        return []
    found: list[Path] = []
    try:
        for path in mount.rglob("*"):
            try:
                if not path.is_file():
                    continue
            except OSError:
                # Broken symlinks, permission errors on random USB layouts, etc.
                continue
            if path.suffix.lower() in VIDEO_EXTENSIONS:
                found.append(path)
    except OSError as exc:
        log.warning("Error walking %s: %s", mount, exc)
    found.sort(key=lambda p: str(p).lower())
    return found


def build_playlist(mounts: list[Path]) -> list[Path]:
    """Sorted union of videos across the given (already mounted) USB paths."""
    all_videos: list[Path] = []
    for mount in mounts:
        vids = list_videos(mount)
        log.info("Mount %s: %d video(s)", mount, len(vids))
        all_videos.extend(vids)
    all_videos.sort(key=lambda p: str(p).lower())
    return all_videos


class UsbMonitor:
    """Background thread publishing udev block-partition events to a queue.

    Only the *fact* that something changed is delivered; the main loop rescans
    mounts on any event, which is cheaper than tracking device state here.
    """

    def __init__(self, events: "queue.Queue[str]") -> None:
        self._events = events
        self._context = pyudev.Context()
        self._monitor = pyudev.Monitor.from_netlink(self._context)
        self._monitor.filter_by(subsystem="block", device_type="partition")
        self._thread = threading.Thread(
            target=self._run, name="usb-monitor", daemon=True
        )
        self._stop = threading.Event()

    def start(self) -> None:
        self._monitor.start()
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        while not self._stop.is_set():
            device = self._monitor.poll(timeout=1.0)
            if device is None:
                continue
            action = device.action or "unknown"
            log.info("udev event: %s %s", action, device.device_node)
            if action in {"add", "change", "remove"}:
                try:
                    self._events.put_nowait(action)
                except queue.Full:
                    # Coalescing: a full queue already signals "something changed".
                    pass
