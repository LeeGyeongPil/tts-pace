"""Piper adapter. Calls a Piper you installed yourself (it is GPL, so it is not a dependency)."""

from __future__ import annotations

import os
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from subprocess import CompletedProcess

from ..audio import AudioClip
from ..errors import EngineError
from ..runtime import DEFAULT_TIMEOUT_S, run_command, run_dir
from .base import EngineInfo
from .say import BuiltCommand

Runner = Callable[..., CompletedProcess[str]]


class PiperEngine:
    """Runs ``python -m piper`` with noise forced to 0 so the output is deterministic.

    Piper's default noise makes every call differ, which breaks caching and makes the measured
    rate wobble. ``speed`` becomes ``--length-scale = 1/speed`` (4 decimals).
    """

    def __init__(
        self,
        voice: str | Path | None = None,
        *,
        command: Sequence[str] | None = None,
        speed_range: tuple[float, float] = (0.6, 1.7),
        sentence_silence: float = 0.8,
        timeout: float = DEFAULT_TIMEOUT_S,
        runner: Runner | None = None,
    ) -> None:
        voice = voice or os.environ.get("TTS_PACE_PIPER_VOICE")
        if not voice:
            raise ValueError(
                "PiperEngine needs a voice .onnx file: pass voice=... or set TTS_PACE_PIPER_VOICE. "
                "Download one with: python -m piper.download_voices en_US-lessac-medium"
            )
        self.voice = str(voice)
        self.command = list(command) if command else [sys.executable, "-m", "piper"]
        self.sentence_silence = sentence_silence
        self.timeout = timeout
        self._runner = runner or run_command
        self.info = EngineInfo(
            name="piper", cache_id=f"piper:{Path(self.voice).name}:ss{sentence_silence}",
            speed_range=speed_range, deterministic=True, has_speed_knob=True,
        )

    def build_command(self, speed: float, out: Path) -> BuiltCommand:
        lo, hi = self.info.speed_range
        applied = min(max(speed, lo), hi)
        argv = [*self.command, "-m", self.voice, "-f", str(out),
                "--length-scale", f"{1.0 / applied:.4f}",
                "--noise-scale", "0", "--noise-w-scale", "0",
                "--sentence-silence", f"{self.sentence_silence:g}"]
        return BuiltCommand(argv, applied, applied != speed)

    def synthesize(self, text: str, speed: float) -> AudioClip:
        with run_dir() as tmp:
            out = tmp / "out.wav"
            built = self.build_command(speed, out)
            self._runner(built.argv, timeout=self.timeout, input_text=text)
            if not out.exists():
                raise EngineError("Piper finished but wrote no audio file. Check the voice path and the piper install.")
            return AudioClip.from_wav(out)
