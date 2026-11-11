"""tts-pace: measure speaking rate and fit TTS output to a target pace.

Public API: count_syllables, measure, retime, fit, fit_audio, AudioClip, the engine adapters
(MockEngine, CallableEngine, SayEngine, PiperEngine), Limiter and the error classes.
Everything else (modules with a leading underscore, helpers inside modules) is internal.
"""

from .audio import AudioClip
from .count import SyllableCount, UnsupportedCharsWarning, count_syllables
from .engines import CallableEngine, EngineInfo, MockEngine, PiperEngine, SayEngine, SpeedEngine
from .errors import (
    AudioFormatError,
    BusyError,
    EngineError,
    MeasurementError,
    TtsPaceError,
    UnsupportedTextError,
)
from .fit import Candidate, FitResult, fit, fit_audio
from .measure import Measurement, measure
from .runtime import Limiter
from .tempo import retime

__version__ = "0.2.0"

__all__ = [
    "AudioClip", "AudioFormatError", "BusyError", "CallableEngine", "Candidate", "EngineError",
    "EngineInfo", "FitResult", "Limiter", "Measurement", "MeasurementError", "MockEngine",
    "PiperEngine", "SayEngine", "SpeedEngine", "SyllableCount", "TtsPaceError",
    "UnsupportedCharsWarning", "UnsupportedTextError", "__version__", "count_syllables", "fit",
    "fit_audio", "measure", "retime",
]
