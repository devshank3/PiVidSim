"""PiVidSim entry point: reconcile USB mounts with mpv playback state.

State machine:
    STOPPED  -> IDLE      on startup with no videos
    STOPPED  -> PLAYING   on startup with videos present
    IDLE     -> PLAYING   USB event and videos are now available
    PLAYING  -> IDLE      USB event and no videos remain
    PLAYING  -> PLAYING   USB event with new set of videos (restart mpv)
    any      -> resurrect if mpv died unexpectedly (watchdog)
"""
from __future__ import annotations

import logging
import queue
import signal
import sys
import time
from types import FrameType
from typing import Optional

from .config import MOUNT_ROOT, SETTLE_SECONDS, WATCHDOG_INTERVAL
from .player import Mode, MpvProcess
from .usb import MountManager, UsbMonitor, build_playlist

log = logging.getLogger("pividsim")


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _drain(q: "queue.Queue[str]") -> None:
    """Discard every pending event; we only care that *something* changed."""
    try:
        while True:
            q.get_nowait()
    except queue.Empty:
        return


def _reconcile(player: MpvProcess, mounts: MountManager) -> None:
    """Match player state to the current set of USB videos."""
    mountpoints = mounts.sync()
    playlist = build_playlist(mountpoints)
    log.info(
        "Reconcile: %d mount(s), %d video file(s) available",
        len(mountpoints), len(playlist),
    )
    if playlist:
        # Always restart on reconcile — cheap, and picks up added/removed files.
        player.start_playing(playlist)
    else:
        # Only switch to idle if we're not already idling.
        if player.mode == Mode.IDLE and player.is_running():
            return
        player.start_idle()


def main() -> int:
    _configure_logging()
    log.info("PiVidSim starting")

    try:
        MOUNT_ROOT.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        log.error("Cannot create mount root %s: %s", MOUNT_ROOT, exc)

    events: "queue.Queue[str]" = queue.Queue(maxsize=64)
    monitor = UsbMonitor(events)
    mounts = MountManager()
    player = MpvProcess()
    stopping = False

    def _handle_signal(signum: int, _frame: Optional[FrameType]) -> None:
        nonlocal stopping
        log.info("Received signal %s; shutting down", signum)
        stopping = True

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    monitor.start()
    _reconcile(player, mounts)

    last_watchdog = time.monotonic()
    try:
        while not stopping:
            try:
                events.get(timeout=WATCHDOG_INTERVAL)
                # Coalesce a burst of events after the first arrival.
                time.sleep(SETTLE_SECONDS)
                _drain(events)
                _reconcile(player, mounts)
            except queue.Empty:
                pass

            now = time.monotonic()
            if now - last_watchdog >= WATCHDOG_INTERVAL:
                if (
                    not player.is_running()
                    and player.mode != Mode.STOPPED
                ):
                    log.warning("mpv died unexpectedly; resurrecting")
                    player.resurrect()
                last_watchdog = now
    finally:
        monitor.stop()
        player.stop()
        mounts.unmount_all()
        log.info("PiVidSim exited")
    return 0


if __name__ == "__main__":
    sys.exit(main())
