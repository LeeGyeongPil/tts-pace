"""Pitch-preserving tempo change: numpy WSOLA, or ffmpeg atempo when available."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from .audio import AudioClip
from .errors import EngineError
from .runtime import DEFAULT_LIMITER, Limiter, find_ffmpeg, run_command, run_dir

DEFAULT_TEMPO_RANGE = (0.85, 1.15)


def clamp_factor(factor: float, tempo_range: tuple[float, float] = DEFAULT_TEMPO_RANGE) -> tuple[float, bool]:
    """Clip a tempo factor into the allowed range. Returns (factor, was_clamped)."""
    lo, hi = tempo_range
    clipped = min(max(factor, lo), hi)
    return clipped, clipped != factor


def wsola(x: np.ndarray, sample_rate: int, factor: float) -> np.ndarray:
    """Waveform-similarity overlap-add time stretch.

    factor > 1 makes the audio faster (shorter), < 1 slower. The output has exactly
    round(len(x) / factor) samples. Pitch is preserved because frames are only moved in time.
    """
    n = len(x)
    out_len = max(1, int(round(n / factor)))
    win = int(round(0.032 * sample_rate))  # 32 ms analysis window
    win += win % 2
    hop_out = win // 2
    delta = int(round(0.012 * sample_rate))  # search +-12 ms around the nominal position
    hop_in = hop_out * factor
    frames = math.ceil(out_len / hop_out) + 1
    pad = win + delta
    xp = np.concatenate([
        np.zeros(pad, np.float32), x.astype(np.float32),
        np.zeros(3 * win + 2 * delta + int(hop_in) + 2, np.float32),
    ])
    energy = np.concatenate(([0.0], np.cumsum(xp.astype(np.float64) ** 2)))
    window = (0.5 - 0.5 * np.cos(2 * np.pi * np.arange(win) / win)).astype(np.float32)
    out = np.zeros(frames * hop_out + win, np.float32)
    wsum = np.zeros_like(out)
    prev = 0
    for k in range(frames):
        nominal = pad + int(round(k * hop_in))
        if k == 0:
            start = nominal
        else:
            template = xp[prev + hop_out: prev + hop_out + win]  # what would naturally follow
            lo = nominal - delta
            seg = xp[lo: nominal + delta + win]
            corr = np.correlate(seg, template, "valid")
            # normalise by the energy of each candidate so loud segments do not always win
            idx = np.arange(2 * delta + 1) + lo
            cand_energy = energy[idx + win] - energy[idx]
            score = corr / np.sqrt(cand_energy + 1e-9)
            start = lo + int(np.argmax(score))
        out[k * hop_out: k * hop_out + win] += xp[start: start + win] * window
        wsum[k * hop_out: k * hop_out + win] += window
        prev = start
    out = out[:out_len]
    wsum = wsum[:out_len]
    return np.where(wsum > 1e-3, out / np.maximum(wsum, 1e-3), 0.0).astype(np.float32)


def _atempo(clip: AudioClip, factor: float) -> AudioClip:
    ffmpeg = find_ffmpeg()
    if ffmpeg is None:
        raise EngineError("backend='ffmpeg' needs ffmpeg. Install it, set TTS_PACE_FFMPEG, or use backend='numpy'.")
    with run_dir() as tmp:
        src = clip.to_wav(tmp / "in.wav")
        dst = tmp / "out.wav"
        run_command([ffmpeg, "-v", "error", "-y", "-i", str(src), "-filter:a", f"atempo={factor:.6f}",
                     "-c:a", "pcm_s16le", str(dst)])
        return AudioClip.from_wav(dst)


def resolve_backend(backend: str) -> str:
    """'auto' becomes 'ffmpeg' when ffmpeg is available, else 'numpy'."""
    if backend not in ("auto", "numpy", "ffmpeg"):
        raise ValueError(f"backend must be 'auto', 'numpy' or 'ffmpeg', got {backend!r}")
    if backend == "auto":
        return "ffmpeg" if find_ffmpeg() else "numpy"
    return backend


def retime(
    audio: str | Path | AudioClip,
    factor: float,
    out: str | Path | None = None,
    backend: str = "auto",
    clamp: bool = False,
    *,
    tempo_range: tuple[float, float] = DEFAULT_TEMPO_RANGE,
    limiter: Limiter | None = None,
) -> AudioClip:
    """Change the speed of ``audio`` by ``factor`` (1.1 = 10% faster) without changing pitch.

    Factors outside ``tempo_range`` (default 0.85-1.15, where artefacts stay small) raise
    ValueError, or are clipped to the nearest bound when ``clamp=True``.
    """
    if not (math.isfinite(factor) and factor > 0):
        raise ValueError(f"factor must be a positive number, got {factor!r}")
    lo, hi = tempo_range
    if not (0 < lo <= 1 <= hi):
        raise ValueError(f"tempo_range must satisfy 0 < low <= 1 <= high, got {tempo_range!r}")
    applied, clamped = clamp_factor(factor, tempo_range)
    if clamped and not clamp:
        raise ValueError(
            f"factor {factor} is outside the allowed tempo range {lo}-{hi}. Large changes sound "
            "artificial: change the text or the engine speed instead, or pass clamp=True to use "
            f"{applied}."
        )
    clip = audio if isinstance(audio, AudioClip) else AudioClip.from_wav(audio)
    used = resolve_backend(backend)
    if applied == 1.0:
        result = clip
    elif used == "ffmpeg":
        with (limiter or DEFAULT_LIMITER).slot():
            result = _atempo(clip, applied)
    else:
        with (limiter or DEFAULT_LIMITER).slot():
            result = AudioClip(wsola(clip.samples, clip.sample_rate, applied), clip.sample_rate)
    if out is not None:
        result.to_wav(out)
    return result
