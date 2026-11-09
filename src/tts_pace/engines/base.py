"""Engine interface. An engine turns text into audio at a relative speed."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from ..audio import AudioClip


@dataclass(frozen=True)
class EngineInfo:
    """Static facts about an engine, used by fit() and for cache keys.

    cache_id: identifies engine + voice + settings; the same id must mean the same sound.
    speed_range: (low, high) relative speeds the engine accepts (1.0 = its default pace).
    deterministic: True when the same text and speed always give the same audio.
    has_speed_knob: False when the engine cannot change pace (fit then only uses tempo).
    is_mock: True for the practice engine, so output can say so honestly.
    """

    name: str
    cache_id: str
    speed_range: tuple[float, float] = (0.5, 2.0)
    deterministic: bool = False
    has_speed_knob: bool = True
    is_mock: bool = False


@runtime_checkable
class SpeedEngine(Protocol):
    """Anything with ``info`` and ``synthesize(text, speed)``; speed 1.0 = default, larger = faster."""

    info: EngineInfo

    def synthesize(self, text: str, speed: float) -> AudioClip: ...
