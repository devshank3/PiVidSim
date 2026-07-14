"""mpv subprocess wrapper with idle/playing modes."""
from __future__ import annotations

import logging
import signal
import subprocess
from enum import Enum
from pathlib import Path

from .config import (
    IDLE_IMAGE,
    MPV_IDLE_ARGS,
    MPV_PLAY_ARGS,
    STOP_TIMEOUT,
)

log = logging.getLogger(__name__)


class Mode(Enum):
    STOPPED = "stopped"
    IDLE = "idle"
    PLAYING = "playing"


class MpvProcess:
    """Owns at most one mpv subprocess. Switches between idle and playing modes."""

    def __init__(self) -> None:
        self._proc: subprocess.Popen | None = None
        self._mode: Mode = Mode.STOPPED
        self._playlist: list[Path] = []

    @property
    def mode(self) -> Mode:
        return self._mode

    @property
    def playlist(self) -> list[Path]:
        return list(self._playlist)

    def is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    # --- Public transitions -------------------------------------------------

    def start_idle(self) -> None:
        if not IDLE_IMAGE.is_file():
            log.error(
                "Idle image missing: %s. Run scripts/generate-idle.py first.",
                IDLE_IMAGE,
            )
            self.stop()
            return
        self._launch(MPV_IDLE_ARGS + [str(IDLE_IMAGE)], Mode.IDLE)
        self._playlist = []

    def start_playing(self, playlist: list[Path]) -> None:
        if not playlist:
            log.warning("start_playing called with empty playlist; going idle")
            self.start_idle()
            return
        args = MPV_PLAY_ARGS + ["--"] + [str(p) for p in playlist]
        self._launch(args, Mode.PLAYING)
        self._playlist = list(playlist)

    def stop(self) -> None:
        if self._proc is None:
            self._mode = Mode.STOPPED
            return
        if self._proc.poll() is None:
            log.info("Stopping mpv (pid=%s)", self._proc.pid)
            try:
                self._proc.send_signal(signal.SIGTERM)
                self._proc.wait(timeout=STOP_TIMEOUT)
            except subprocess.TimeoutExpired:
                log.warning("mpv did not exit on SIGTERM; sending SIGKILL")
                self._proc.kill()
                try:
                    self._proc.wait(timeout=STOP_TIMEOUT)
                except subprocess.TimeoutExpired:
                    log.error("mpv (pid=%s) unresponsive to SIGKILL", self._proc.pid)
            except OSError as exc:
                log.warning("Error stopping mpv: %s", exc)
        self._proc = None
        self._mode = Mode.STOPPED

    def resurrect(self) -> None:
        """If mpv died while we still expect it to run, restart the same mode."""
        if self.is_running():
            return
        prior = self._mode
        # Clear stale handle first so _launch's stop() call is a no-op.
        self._proc = None
        if prior == Mode.PLAYING and self._playlist:
            log.info("Watchdog: restarting player (playing)")
            self.start_playing(self._playlist)
        elif prior == Mode.IDLE:
            log.info("Watchdog: restarting player (idle)")
            self.start_idle()

    # --- Internals ----------------------------------------------------------

    def _launch(self, args: list[str], new_mode: Mode) -> None:
        self.stop()
        log.info("Launching mpv (mode=%s, argc=%d)", new_mode.value, len(args))
        try:
            self._proc = subprocess.Popen(
                args,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self._mode = new_mode
        except FileNotFoundError:
            log.error("mpv binary not found on PATH")
            self._proc = None
            self._mode = Mode.STOPPED
        except OSError as exc:
            log.error("Failed to launch mpv: %s", exc)
            self._proc = None
            self._mode = Mode.STOPPED
