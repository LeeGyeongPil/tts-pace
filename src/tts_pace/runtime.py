"""Resource handling: concurrency limiter, per-run temp folders, subprocess with timeout."""

from __future__ import annotations

import contextlib
import os
import shutil
import subprocess
import tempfile
import threading
from collections.abc import Iterator, Sequence
from pathlib import Path

from .errors import BusyError, EngineError

DEFAULT_TIMEOUT_S = 120.0


class Limiter:
    """Bound how many heavy steps (synthesis, tempo, ffmpeg) run at once.

    At most ``max_concurrent`` steps run; up to ``max_waiting`` more wait for a slot;
    anything beyond that raises BusyError immediately instead of piling up.
    """

    def __init__(self, max_concurrent: int = 2, max_waiting: int = 8) -> None:
        if max_concurrent < 1:
            raise ValueError("max_concurrent must be >= 1")
        if max_waiting < 0:
            raise ValueError("max_waiting must be >= 0")
        self.max_concurrent = max_concurrent
        self.max_waiting = max_waiting
        self._cond = threading.Condition()
        self._active = 0
        self._waiting = 0

    @contextlib.contextmanager
    def slot(self) -> Iterator[None]:
        """Hold one slot for the duration of the ``with`` block."""
        with self._cond:
            if self._active >= self.max_concurrent:
                if self._waiting >= self.max_waiting:
                    raise BusyError(
                        f"All {self.max_concurrent} slot(s) are busy and {self._waiting} request(s) "
                        "are already waiting. Retry later or raise Limiter(max_waiting=...).",
                        code="busy", params={"slots": self.max_concurrent, "waiting": self._waiting},
                    )
                self._waiting += 1
                try:
                    while self._active >= self.max_concurrent:
                        self._cond.wait()
                finally:
                    self._waiting -= 1
            self._active += 1
        try:
            yield
        finally:
            with self._cond:
                self._active -= 1
                self._cond.notify()


DEFAULT_LIMITER = Limiter()


@contextlib.contextmanager
def run_dir() -> Iterator[Path]:
    """A fresh temp folder for one run; always removed, even when the body raises."""
    path = Path(tempfile.mkdtemp(prefix="tts-pace-"))
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def find_ffmpeg() -> str | None:
    """Path of the ffmpeg executable: TTS_PACE_FFMPEG, else PATH, else None."""
    env = os.environ.get("TTS_PACE_FFMPEG")
    if env:
        return env if shutil.which(env) or Path(env).exists() else None
    return shutil.which("ffmpeg")


def run_command(
    argv: Sequence[str],
    *,
    timeout: float = DEFAULT_TIMEOUT_S,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run an external program with a timeout; every failure becomes EngineError."""
    name = argv[0] if argv else "(empty command)"
    try:
        proc = subprocess.run(
            list(argv),
            input=input_text,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise EngineError(
            f"{name} did not finish within {timeout:g}s. Real engines can be slow on a busy "
            "machine: raise the timeout or try a shorter text.",
            code="engine_timeout", params={"name": name, "timeout": timeout},
        ) from exc
    except FileNotFoundError as exc:
        raise EngineError(f"{name} was not found. Install it or give its full path.",
                          code="engine_not_found", params={"name": name}) from exc
    except OSError as exc:
        raise EngineError(f"{name} could not be started: {exc}",
                          code="engine_start_failed", params={"name": name, "reason": str(exc)}) from exc
    if proc.returncode != 0:
        tail = (proc.stderr or "").strip().splitlines()[-3:]
        raise EngineError(f"{name} exited with code {proc.returncode}: {' | '.join(tail)}",
                          code="engine_exit",
                          params={"name": name, "returncode": proc.returncode, "tail": " | ".join(tail)})
    return proc
