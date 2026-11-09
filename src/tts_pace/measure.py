"""Articulation-rate measurement: syllables divided by speech time without long silences."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .audio import AudioClip
from .count import count_syllables
from .errors import MeasurementError
from .runtime import Limiter, DEFAULT_LIMITER, find_ffmpeg, run_command, run_dir

FRAME_S = 0.005  # numpy backend looks at 5 ms frames; a frame is quiet if its peak is below the threshold


@dataclass(frozen=True)
class Measurement:
    """One measurement.

    total_s: clip length. silence_s: sum of silences at least ``min_silence`` long (leading and
    trailing included). net_s = total_s - silence_s is the pure speech time. ``gaps`` counts those
    silences. ``sps`` = syllables / net_s, or None when no text or syllable count was given.
    """

    total_s: float
    silence_s: float
    net_s: float
    gaps: int
    syllables: int | None
    sps: float | None
    silence_db: float
    min_silence: float
    backend: str

    def to_dict(self) -> dict[str, object]:
        return {
            "total_s": round(self.total_s, 4),
            "silence_s": round(self.silence_s, 4),
            "net_s": round(self.net_s, 4),
            "gaps": self.gaps,
            "syllables": self.syllables,
            "sps": None if self.sps is None else round(self.sps, 4),
            "silence_db": self.silence_db,
            "min_silence": self.min_silence,
            "backend": self.backend,
        }

    @classmethod
    def from_dict(cls, d: dict[str, object]) -> Measurement:
        return cls(
            float(d["total_s"]), float(d["silence_s"]), float(d["net_s"]), int(d["gaps"]),  # type: ignore[arg-type]
            None if d["syllables"] is None else int(d["syllables"]),  # type: ignore[arg-type]
            None if d["sps"] is None else float(d["sps"]),  # type: ignore[arg-type]
            float(d["silence_db"]), float(d["min_silence"]), str(d["backend"]),  # type: ignore[arg-type]
        )


def _silences_numpy(clip: AudioClip, silence_db: float, min_silence: float) -> list[float]:
    x = np.abs(clip.samples)
    n = len(x)
    frame = max(1, round(FRAME_S * clip.sample_rate))
    nf = math.ceil(n / frame)
    padded = np.zeros(nf * frame, dtype=np.float32)
    padded[:n] = x
    quiet = padded.reshape(nf, frame).max(axis=1) <= 10 ** (silence_db / 20.0)
    edges = np.diff(np.concatenate(([0], quiet.astype(np.int8), [0])))
    starts, ends = np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)
    runs = []
    for s, e in zip(starts, ends):
        dur = (min(int(e) * frame, n) - int(s) * frame) / clip.sample_rate
        if dur >= min_silence:
            runs.append(dur)
    return runs


def _silences_ffmpeg(clip: AudioClip, silence_db: float, min_silence: float) -> list[float]:
    ffmpeg = find_ffmpeg()
    if ffmpeg is None:
        raise MeasurementError(
            "backend='ffmpeg' needs ffmpeg. Install it, set TTS_PACE_FFMPEG, or use backend='numpy'."
        )
    with run_dir() as tmp:
        wav = clip.to_wav(tmp / "in.wav")
        proc = run_command([
            ffmpeg, "-hide_banner", "-nostats", "-i", str(wav),
            "-af", f"silencedetect=noise={silence_db}dB:d={min_silence}", "-f", "null", "-",
        ])
    runs: list[float] = []
    open_start: float | None = None
    for line in proc.stderr.splitlines():
        m = re.search(r"silence_start: (-?[\d.]+)", line)
        if m:
            open_start = max(float(m.group(1)), 0.0)
        m = re.search(r"silence_duration: ([\d.]+)", line)
        if m:
            runs.append(float(m.group(1)))
            open_start = None
    if open_start is not None:  # silence that runs to the end of the file has no silence_end line
        runs.append(clip.duration - open_start)
    return runs


def measure(
    audio: str | Path | AudioClip,
    text: str | None = None,
    syllables: int | None = None,
    *,
    silence_db: float = -60.0,
    min_silence: float = 0.6,
    backend: str = "auto",
    limiter: Limiter | None = None,
) -> Measurement:
    """Measure the pure-speech time and, when text or a syllable count is given, the rate.

    backend: 'numpy' (no dependencies), 'ffmpeg' (silencedetect), or 'auto' (= numpy, so results
    do not change depending on what is installed).
    """
    if backend not in ("auto", "numpy", "ffmpeg"):
        raise ValueError(f"backend must be 'auto', 'numpy' or 'ffmpeg', got {backend!r}")
    if text is not None and syllables is not None:
        raise ValueError("Give either text or syllables, not both.")
    if min_silence <= 0:
        raise ValueError("min_silence must be > 0 seconds")
    if silence_db >= 0:
        raise ValueError("silence_db must be negative (dBFS), e.g. -60")
    clip = audio if isinstance(audio, AudioClip) else AudioClip.from_wav(audio)
    if text is not None:
        syllables = count_syllables(text).total
    used = "ffmpeg" if backend == "ffmpeg" else "numpy"
    if used == "ffmpeg":
        with (limiter or DEFAULT_LIMITER).slot():
            runs = _silences_ffmpeg(clip, silence_db, min_silence)
    else:
        runs = _silences_numpy(clip, silence_db, min_silence)
    total = clip.duration
    silence = min(sum(runs), total)
    net = total - silence
    if net <= 1e-3:
        raise MeasurementError(
            "The clip has no speech: everything is silence at the chosen threshold "
            f"({silence_db} dB, min {min_silence}s). Check the file, or lower silence_db "
            "(for example -50) if the recording has a noise floor."
        )
    sps = None if syllables is None else syllables / net
    return Measurement(total, silence, net, len(runs), syllables, sps, silence_db, min_silence, used)
