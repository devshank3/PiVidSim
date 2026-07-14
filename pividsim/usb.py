"""USB mount discovery and udev-based hot-plug monitoring."""
from __future__ import annotations

import logging
import queue
import threading
from pathlib import Path
from typing import Iterator

import pyudev

from .config import MOUNT_ROOT, USB_FS_TYPES, VIDEO_EXTENSIONS

log = logging.getLogger(__name__)


def iter_current_usb_mounts() -> Iterator[Path]:
    """Yield mount paths under MOUNT_ROOT that look like USB drives."""
    try:
        raw = Path("/proc/mounts").read_text()
    except OSError as exc:
        log.warning("Could not read /proc/mounts: %s", exc)
        return

    for line in raw.splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        _dev, mountpoint, fstype = parts[0], parts[1], parts[2]
        if fstype not in USB_FS_TYPES:
            continue

        # /proc/mounts encodes spaces/tabs as octal escapes (\040, \011...).
        try:
            mp = mountpoint.encode("latin-1").decode("unicode_escape")
        except UnicodeDecodeError:
            mp = mountpoint

        mp_path = Path(mp)
        try:
            mp_path.relative_to(MOUNT_ROOT)
        except ValueError:
            continue
        yield mp_path


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


def build_playlist() -> list[Path]:
    """Sorted union of videos across all currently mounted USB drives."""
    all_videos: list[Path] = []
    for mount in iter_current_usb_mounts():
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
