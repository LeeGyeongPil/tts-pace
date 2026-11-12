"""Exception hierarchy. Everything tts-pace raises on purpose derives from TtsPaceError.

Errors may carry an optional ``code`` and ``params`` so the command line can show the message in
the user's screen language. ``str(exc)`` is always the English message, so library users see no change.
"""

from __future__ import annotations

from typing import Any


class TtsPaceError(Exception):
    """Base class for all tts-pace errors.

    ``code`` and ``params`` (both optional, keyword-only) name a message in ``tts_pace.i18n``.
    """

    def __init__(self, message: str = "", *args: object, code: str | None = None,
                 params: dict[str, Any] | None = None) -> None:
        super().__init__(message, *args)
        self.code = code
        self.params: dict[str, Any] = dict(params or {})


class CodedValueError(ValueError):
    """A ValueError for bad arguments that also carries ``code``/``params`` for the CLI."""

    def __init__(self, message: str = "", *, code: str | None = None,
                 params: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.params: dict[str, Any] = dict(params or {})


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
