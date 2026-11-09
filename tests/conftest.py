"""Shared helpers: audio fixtures are synthesized with numpy, nothing is downloaded."""

from __future__ import annotations

import numpy as np
import pytest

SR = 22050


def burst(dur: float = 0.15, freq: float = 140.0) -> np.ndarray:
    n = int(round(dur * SR))
    t = np.arange(n) / SR
    env = np.hanning(n + 2)[1:-1]
    tone = 0.5 * np.sin(2 * np.pi * freq * t) + 0.25 * np.sin(2 * np.pi * 2 * freq * t)
    return (0.6 * tone * env).astype(np.float32)


def silence(dur: float) -> np.ndarray:
    return np.zeros(int(round(dur * SR)), np.float32)


def bursts(n: int, dur: float = 0.15) -> np.ndarray:
    return np.concatenate([burst(dur) for _ in range(n)])


@pytest.fixture
def speech_fixture() -> np.ndarray:
    """20 bursts, 0.9 s silence, 0.4 s short pause, trailing 0.7 s silence."""
    return np.concatenate([bursts(10), silence(0.9), bursts(5), silence(0.4), bursts(5), silence(0.7)])
