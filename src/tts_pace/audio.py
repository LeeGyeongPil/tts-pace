"""Mono float audio and WAV reading/writing (standard library `wave` + numpy)."""

from __future__ import annotations

import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .errors import AudioFormatError, EngineError
from .runtime import find_ffmpeg, run_command, run_dir


@dataclass(frozen=True)
class AudioClip:
    """Mono audio: ``samples`` is float32 in [-1, 1]."""

    samples: np.ndarray
    sample_rate: int

    def __post_init__(self) -> None:
        if self.sample_rate <= 0:
            raise ValueError("sample_rate must be positive")
        if self.samples.ndim != 1:
            raise ValueError("samples must be a 1-D (mono) array")
        if self.samples.dtype != np.float32:
            object.__setattr__(self, "samples", self.samples.astype(np.float32))

    @property
    def duration(self) -> float:
        return len(self.samples) / self.sample_rate

    @classmethod
    def from_wav(cls, path: str | Path) -> AudioClip:
        """Read a WAV (8/16/24/32-bit PCM). Other formats are decoded with ffmpeg when available."""
        p = Path(path)
        if not p.exists():
            raise AudioFormatError(f"Audio file not found: {p}", code="audio_not_found", params={"path": str(p)})
        try:
            return _read_pcm_wav(p)
        except (wave.Error, EOFError):
            return _decode_with_ffmpeg(p)

    def to_wav(self, path: str | Path) -> Path:
        """Write 16-bit PCM WAV and return the path."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        pcm = np.clip(self.samples, -1.0, 1.0)
        data = (pcm * 32767.0).round().astype("<i2").tobytes()
        with wave.open(str(p), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(self.sample_rate)
            w.writeframes(data)
        return p


def _read_pcm_wav(p: Path) -> AudioClip:
    with wave.open(str(p), "rb") as w:
        ch, width, rate, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
        raw = w.readframes(n)
    if n == 0:
        raise AudioFormatError(f"{p} has no audio frames.", code="audio_no_frames", params={"path": str(p)})
    if width == 1:
        x = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    elif width == 2:
        x = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    elif width == 3:
        b = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3).astype(np.int32)
        v = b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)
        v = np.where(v >= 1 << 23, v - (1 << 24), v)
        x = v.astype(np.float32) / float(1 << 23)
    elif width == 4:
        x = np.frombuffer(raw, dtype="<i4").astype(np.float32) / float(1 << 31)
    else:
        raise AudioFormatError(f"Unsupported sample width {width} bytes in {p}.",
                               code="audio_bad_width", params={"width": width, "path": str(p)})
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)  # mix down to mono
    return AudioClip(x.astype(np.float32), rate)


def _decode_with_ffmpeg(p: Path) -> AudioClip:
    ffmpeg = find_ffmpeg()
    if ffmpeg is None:
        raise AudioFormatError(
            f"{p} is not a PCM WAV file and ffmpeg was not found to decode it. "
            "Convert it to 16-bit WAV, or install ffmpeg (or set TTS_PACE_FFMPEG).",
            code="audio_no_ffmpeg", params={"path": str(p)},
        )
    with run_dir() as tmp:
        out = tmp / "decoded.wav"
        try:
            run_command([ffmpeg, "-v", "error", "-y", "-i", str(p), "-ac", "1", "-c:a", "pcm_s16le", str(out)])
        except EngineError as exc:
            raise AudioFormatError(
                f"{p} is not an audio file ffmpeg can read; convert it to 16-bit WAV. (ffmpeg said: {exc})",
                code="audio_ffmpeg_unreadable", params={"path": str(p), "reason": str(exc)},
            ) from exc
        return _read_pcm_wav(out)
