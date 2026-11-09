"""macOS `say` adapter (Korean voices such as Yuna work well)."""

from __future__ import annotations

import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from subprocess import CompletedProcess

from ..audio import AudioClip
from ..errors import AudioFormatError, EngineError
from ..runtime import DEFAULT_TIMEOUT_S, run_command, run_dir
from .base import EngineInfo

Runner = Callable[..., CompletedProcess[str]]


@dataclass(frozen=True)
class BuiltCommand:
    argv: list[str]
    applied_speed: float
    clamped: bool  # True when the requested speed was outside the engine range and was cut


class SayEngine:
    """Calls `say -r <words per minute>`; ``speed`` multiplies ``base_wpm``.

    `say -r` silently stops responding below about 150 wpm (probe, 2026-11-09), so the default
    range is 0.86-1.6 of 175 wpm. fit() warns with knob_clamped when it has to cut a request.
    """

    def __init__(
        self,
        voice: str | None = None,
        *,
        base_wpm: int = 175,
        speed_range: tuple[float, float] = (0.86, 1.6),
        timeout: float = DEFAULT_TIMEOUT_S,
        runner: Runner | None = None,
    ) -> None:
        self.voice = voice
        self.base_wpm = base_wpm
        self.timeout = timeout
        self._runner = runner or run_command
        self.info = EngineInfo(
            name="say", cache_id=f"say:{voice or 'default'}:{base_wpm}", speed_range=speed_range,
            deterministic=True, has_speed_knob=True,
        )

    def build_command(self, speed: float, out: Path, text_file: Path) -> BuiltCommand:
        lo, hi = self.info.speed_range
        applied = min(max(speed, lo), hi)
        argv = ["say"]
        if self.voice:
            argv += ["-v", self.voice]
        argv += ["-r", str(round(self.base_wpm * applied)), "-o", str(out),
                 "--file-format=WAVE", "--data-format=LEI16@22050", "-f", str(text_file)]
        return BuiltCommand(argv, applied, applied != speed)

    def synthesize(self, text: str, speed: float) -> AudioClip:
        if sys.platform != "darwin" and self._runner is run_command:
            raise EngineError("SayEngine only works on macOS. Use CallableEngine for other platforms.")
        with run_dir() as tmp:
            text_file = tmp / "text.txt"
            text_file.write_text(text, encoding="utf-8")
            out = tmp / "out.wav"
            built = self.build_command(speed, out, text_file)
            self._runner(built.argv, timeout=self.timeout)
            try:
                return AudioClip.from_wav(out)
            except AudioFormatError as exc:
                raise EngineError(
                    f"say wrote no audio ({exc}). Check the voice name (`say -v '?'`) and that the "
                    "process is allowed to use macOS speech synthesis (some sandboxes block it)."
                ) from exc
