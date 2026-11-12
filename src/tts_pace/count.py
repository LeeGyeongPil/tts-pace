"""Syllable counting from text: Korean blocks, English heuristic, Japanese morae."""

from __future__ import annotations

import re
import warnings
from collections.abc import Mapping
from dataclasses import dataclass, field

from .en_syllables import count_en_word
from .errors import UnsupportedTextError
from .normalize import normalize_text

_SMALL_KANA = set("ゃゅょぁぃぅぇぉゎャュョァィゥェォヮ")  # glue onto the previous kana (1 mora together)


@dataclass(frozen=True)
class SyllableCount:
    """Result of count_syllables().

    total: syllables (Korean/English) plus morae (Japanese) that were counted.
    by_script: counts per script, keys 'ko', 'en', 'ja'.
    normalized_text: the spoken form that was counted (digits and acronyms expanded).
    unsupported: characters or tokens that could not be counted (e.g. kanji).
    """

    total: int
    by_script: dict[str, int] = field(default_factory=lambda: {"ko": 0, "en": 0, "ja": 0})
    normalized_text: str = ""
    unsupported: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "total": self.total,
            "by_script": dict(self.by_script),
            "normalized_text": self.normalized_text,
            "unsupported": list(self.unsupported),
        }


class UnsupportedCharsWarning(UserWarning):
    """Some characters (kanji, digits in Japanese text) were not counted."""


def count_normalized(spoken: str) -> tuple[dict[str, int], list[str]]:
    """Count an already normalized text. Returns (by_script, unsupported characters)."""
    by = {"ko": 0, "en": 0, "ja": 0}
    unsupported: list[str] = []
    for m in re.finditer(r"[가-힣]|[A-Za-z][A-Za-z'’]*|[぀-ヿ]|[一-鿿㐀-䶿]", spoken):
        tok = m.group(0)
        c = tok[0]
        if "가" <= c <= "힣":
            by["ko"] += 1
        elif c.isascii() and c.isalpha():
            by["en"] += count_en_word(tok)
        elif "぀" <= c <= "ヿ":
            if c in _SMALL_KANA or c in "・゛゜゠":
                continue  # part of the previous mora (きょ = 1) or punctuation
            by["ja"] += 1  # a kana, っ, ん and the long-vowel mark ー each count as one mora
        else:
            unsupported.append(tok)
    return by, unsupported


def count_syllables(
    text: str,
    lang: str = "auto",
    normalize: Mapping[str, str] | None = None,
) -> SyllableCount:
    """Count the syllables of ``text`` the way a TTS engine would read it.

    ``lang`` ('auto', 'ko', 'en', 'ja') only decides how digits and ACRONYMS are read;
    letters are always counted by their own script. ``normalize`` maps text to a spoken
    form before anything else, e.g. ``{"2026": "twenty twenty six"}``.

    Raises UnsupportedTextError when nothing countable remains.
    """
    if not isinstance(text, str):
        raise TypeError(f"text must be str, got {type(text).__name__}")
    spoken, bad_tokens = normalize_text(text, lang, normalize)
    by, bad_chars = count_normalized(spoken)
    unsupported = tuple(bad_tokens + bad_chars)
    total = sum(by.values())
    if total == 0:
        raise UnsupportedTextError(
            "No countable syllables found in the text"
            + (f" (unsupported: {', '.join(unsupported)})" if unsupported else "")
            + ". Provide Hangul, kana or Latin letters, or map the text to a spoken form "
            "with normalize={...}.",
            code="unsupported_text" if not unsupported else "unsupported_text_detail",
            params={"unsupported": ", ".join(unsupported)},
        )
    if unsupported:
        warnings.warn(
            f"{len(unsupported)} unsupported token(s) were not counted: {', '.join(unsupported[:5])}"
            f"{'...' if len(unsupported) > 5 else ''}. Counts will be low; use normalize={{...}} "
            "to give a kana/Hangul reading.",
            UnsupportedCharsWarning,
            stacklevel=2,
        )
    return SyllableCount(total, by, spoken, unsupported)
