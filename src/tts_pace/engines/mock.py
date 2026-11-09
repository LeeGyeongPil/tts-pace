"""Practice (mock) engine: NOT a real TTS. It builds voice-like tone bursts, one per syllable.

It exists so the whole fit loop runs without keys or models, and it reproduces three
behaviours seen with real engines (see README, "what we learned"):

* the speed knob is not proportional:   real rate = base_sps * speed ** elasticity
* some knobs silently stop at a floor:  speeds below ``silent_floor`` change nothing
* some engines are not deterministic:   ``jitter > 0`` makes every call a little different
"""

from __future__ import annotations

import re

import numpy as np

from ..audio import AudioClip
from ..count import count_normalized
from ..normalize import normalize_text
from .base import EngineInfo

SAMPLE_RATE = 22050
WORD_GAP_S = 0.05  # short pause between words: stays inside the speech time
PRESETS = {
    # English-like: the knob answers weakly (Piper length_scale showed about 55% of the expected change)
    "en": {"base_sps": 4.6, "elasticity": 0.6, "silent_floor": 0.0},
    # Korean-like: knob almost proportional but stops at a floor (macOS `say -r` below ~150 wpm)
    "ko": {"base_sps": 5.4, "elasticity": 0.95, "silent_floor": 0.9},
}


class MockEngine:
    """Practice engine. ``MockEngine("en")`` or ``MockEngine("ko")``; every value can be overridden."""

    def __init__(
        self,
        preset: str = "en",
        *,
        base_sps: float | None = None,
        elasticity: float | None = None,
        silent_floor: float | None = None,
        jitter: float = 0.0,
        speed_range: tuple[float, float] = (0.5, 2.0),
        sentence_pause_s: float = 0.8,
        end_pause_s: float = 0.9,
        seed: int | None = None,
    ) -> None:
        if preset not in PRESETS:
            raise ValueError(f"preset must be one of {sorted(PRESETS)}, got {preset!r}")
        p = PRESETS[preset]
        self.base_sps = p["base_sps"] if base_sps is None else base_sps
        self.elasticity = p["elasticity"] if elasticity is None else elasticity
        self.silent_floor = p["silent_floor"] if silent_floor is None else silent_floor
        if self.base_sps <= 0 or self.elasticity <= 0:
            raise ValueError("base_sps and elasticity must be positive")
        if not 0 <= jitter < 1:
            raise ValueError("jitter must be in [0, 1)")
        self.jitter = jitter
        self.sentence_pause_s = sentence_pause_s
        self.end_pause_s = end_pause_s
        self._rng = np.random.default_rng(seed)  # seed=None draws OS entropy: truly non-deterministic
        self.calls: list[float] = []  # speeds this engine was asked for (tests count calls with this)
        self.info = EngineInfo(
            name=f"mock-{preset}",
            cache_id=(f"mock:{preset}:{self.base_sps}:{self.elasticity}:{self.silent_floor}:"
                      f"{jitter}:{sentence_pause_s}:{end_pause_s}"),
            speed_range=speed_range,
            deterministic=jitter == 0,
            has_speed_knob=True,
            is_mock=True,
        )

    def rate_for(self, speed: float) -> float:
        """The articulation rate (syllables per second) this engine produces at ``speed``."""
        effective = max(speed, self.silent_floor)  # below the floor the knob does nothing
        return self.base_sps * effective ** self.elasticity

    def synthesize(self, text: str, speed: float) -> AudioClip:
        if speed <= 0:
            raise ValueError("speed must be positive")
        self.calls.append(speed)
        slot = 1.0 / self.rate_for(speed)  # seconds per syllable, word gaps included
        spoken, _ = normalize_text(text)
        sentences = [s for s in re.split(r"(?<=[.!?。！？])\s+|\n+", spoken) if s.strip()]
        pieces: list[np.ndarray] = []
        for si, sentence in enumerate(sentences):
            words = [w for w in sentence.split() if sum(count_normalized(w)[0].values()) > 0]
            for wi, word in enumerate(words):
                n = sum(count_normalized(word)[0].values())
                for k in range(n):
                    dur = slot * (1 + self.jitter * self._rng.uniform(-1, 1)) if self.jitter else slot
                    last_of_word = k == n - 1 and wi < len(words) - 1
                    gap = min(WORD_GAP_S, 0.25 * dur) if last_of_word else 0.0
                    pieces.append(_burst(dur - gap))
                    if gap:
                        pieces.append(np.zeros(int(round(gap * SAMPLE_RATE)), np.float32))
            last = si == len(sentences) - 1
            pause = self.end_pause_s if last else self.sentence_pause_s
            pieces.append(np.zeros(int(round(pause * SAMPLE_RATE)), np.float32))
        if not pieces:
            pieces.append(np.zeros(int(self.end_pause_s * SAMPLE_RATE), np.float32))
        return AudioClip(np.concatenate(pieces), SAMPLE_RATE)


def _burst(duration: float) -> np.ndarray:
    """One syllable: a 140 Hz tone with two overtones under a Hann envelope."""
    n = max(1, int(round(duration * SAMPLE_RATE)))
    t = np.arange(n) / SAMPLE_RATE
    f0 = 140.0
    tone = 0.5 * np.sin(2 * np.pi * f0 * t) + 0.25 * np.sin(2 * np.pi * 2 * f0 * t) \
        + 0.12 * np.sin(2 * np.pi * 3 * f0 * t)
    envelope = np.hanning(n + 2)[1:-1]
    return (0.6 * tone * envelope).astype(np.float32)
