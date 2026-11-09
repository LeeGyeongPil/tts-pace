"""Exception hierarchy. Everything tts-pace raises on purpose derives from TtsPaceError."""

from __future__ import annotations


class TtsPaceError(Exception):
    """Base class for all tts-pace errors."""


class EngineError(TtsPaceError):
    """A TTS engine or external tool (ffmpeg, say, piper) failed, timed out or is missing."""


class AudioFormatError(TtsPaceError):
    """The audio could not be read (unsupported WAV format, missing decoder, empty data)."""


class MeasurementError(TtsPaceError):
    """The speaking rate cannot be measured (for example the clip is entirely silent)."""


class UnsupportedTextError(TtsPaceError):
    """The text has no countable syllables (only unsupported characters or no letters)."""


class BusyError(TtsPaceError):
    """The Limiter has no free slot and its waiting room is full; retry later."""
