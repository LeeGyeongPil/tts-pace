"""Wrap any function as an engine: ``CallableEngine(lambda text, speed: my_tts(text, rate=speed))``."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import numpy as np

from ..audio import AudioClip
from ..errors import EngineError
from .base import EngineInfo


class CallableEngine:
    """Adapter for any TTS you can call from Python (cloud APIs, local models).

    ``fn(text, speed)`` must return an AudioClip, a path to a WAV file, or a
    ``(samples, sample_rate)`` tuple. ``speed`` is passed through unchanged:
    1.0 = the engine's default pace, larger = faster; convert to your engine's unit inside ``fn``.
    """

    def __init__(
        self,
        fn: Callable[[str, float], AudioClip | str | Path | tuple[np.ndarray, int]],
        *,
        speed_range: tuple[float, float] = (0.5, 2.0),
        deterministic: bool = False,
        cache_id: str | None = None,
        name: str = "callable",
        has_speed_knob: bool = True,
    ) -> None:
        if not callable(fn):
            raise TypeError("fn must be callable as fn(text, speed)")
        if deterministic and not cache_id:
            raise ValueError(
                "deterministic=True needs a cache_id that names the engine, voice and settings "
                "(for example cache_id='my-tts:voiceA'), otherwise cached results could be mixed up."
            )
        if not 0 < speed_range[0] <= speed_range[1]:
            raise ValueError(f"speed_range must be (low, high) with 0 < low <= high, got {speed_range!r}")
        self._fn = fn
        self.info = EngineInfo(name, cache_id or f"{name}:uncached", speed_range, deterministic, has_speed_knob)

    def synthesize(self, text: str, speed: float) -> AudioClip:
        result = self._fn(text, speed)
        if isinstance(result, AudioClip):
            return result
        if isinstance(result, (str, Path)):
            return AudioClip.from_wav(result)
        if isinstance(result, tuple) and len(result) == 2:
            return AudioClip(np.asarray(result[0], dtype=np.float32), int(result[1]))
        raise EngineError(
            "The function given to CallableEngine must return an AudioClip, a WAV path or "
            f"(samples, sample_rate); it returned {type(result).__name__}."
        )
