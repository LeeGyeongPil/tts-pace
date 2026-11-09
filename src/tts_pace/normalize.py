"""Turn digits and acronyms into a spoken form so that syllables can be counted from text.

The spoken form depends on the language *context* of the sentence the token is in:
Korean (Hangul present), Japanese (kana present) or English (everything else).
"""

from __future__ import annotations

import re
from collections.abc import Mapping

# Letter names used when an ALL-CAPS acronym (2-5 letters) is spelled out.
_EN_LETTERS = dict(zip(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
    ["ay", "bee", "see", "dee", "ee", "eff", "jee", "aitch", "eye", "jay", "kay", "ell", "em",
     "en", "oh", "pee", "cue", "ar", "ess", "tee", "you", "vee", "double you", "ex", "why", "zee"],
))
_KO_LETTERS = dict(zip(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
    ["에이", "비", "씨", "디", "이", "에프", "지", "에이치", "아이", "제이", "케이", "엘", "엠",
     "엔", "오", "피", "큐", "알", "에스", "티", "유", "브이", "더블유", "엑스", "와이", "제트"],
))

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?。！？])\s+|\n+")
_NUMBER = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?%?|\d+(?:\.\d+)?%?")
_ACRONYM = re.compile(r"(?<![A-Za-z])[A-Z]{2,5}(?![A-Za-z])")

_SINO_DIGITS = "영일이삼사오육칠팔구"
_SMALL_UNITS = ["", "십", "백", "천"]
_BIG_UNITS = ["", "만", "억", "조", "경"]

_EN_ONES = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
            "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen",
            "eighteen", "nineteen"]
_EN_TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]
_EN_BIG = ["", "thousand", "million", "billion", "trillion"]


def context_of(sentence: str, lang: str = "auto") -> str:
    """Return 'ko', 'ja' or 'en' for one sentence (an explicit lang wins over detection)."""
    if lang in ("ko", "ja", "en"):
        return lang
    if re.search(r"[가-힣]", sentence):
        return "ko"
    if re.search(r"[぀-ヿ]", sentence):
        return "ja"
    return "en"


def ko_number(digits: str) -> str:
    """Sino-Korean reading of an integer string: '2026' -> '이천이십육'."""
    if not digits.isdigit():
        raise ValueError(f"not an integer string: {digits!r}")
    if len(digits) > 20 or (len(digits) > 1 and digits[0] == "0"):
        return "".join(_SINO_DIGITS[int(d)] for d in digits)  # too long or zero padded: digit by digit
    n = int(digits)
    if n == 0:
        return "영"
    parts: list[str] = []
    group = 0
    while n > 0:
        n, chunk = divmod(n, 10000)
        if chunk:
            text = ""
            for pos in range(3, -1, -1):
                d = (chunk // 10 ** pos) % 10
                if d == 0:
                    continue
                # 1 is omitted before 십/백/천 ("십", not "일십"); a bare 1 stays "일"
                text += ("" if d == 1 and pos > 0 else _SINO_DIGITS[d]) + _SMALL_UNITS[pos]
            if text == "일" and group > 0:
                text = ""  # "만", not "일만"
            parts.append(text + _BIG_UNITS[group])
        group += 1
    return "".join(reversed(parts))


def en_number(digits: str) -> str:
    """English cardinal reading: '2026' -> 'two thousand twenty six'."""
    if not digits.isdigit():
        raise ValueError(f"not an integer string: {digits!r}")
    if len(digits) > 15 or (len(digits) > 1 and digits[0] == "0"):
        return " ".join(_EN_ONES[int(d)] for d in digits)
    n = int(digits)
    if n < 20:
        return _EN_ONES[n]
    words: list[str] = []
    group = 0
    while n > 0:
        n, chunk = divmod(n, 1000)
        if chunk:
            part: list[str] = []
            hundreds, rest = divmod(chunk, 100)
            if hundreds:
                part += [_EN_ONES[hundreds], "hundred"]
            if rest >= 20:
                part.append(_EN_TENS[rest // 10])
                if rest % 10:
                    part.append(_EN_ONES[rest % 10])
            elif rest:
                part.append(_EN_ONES[rest])
            if _EN_BIG[group]:
                part.append(_EN_BIG[group])
            words = part + words
        group += 1
    return " ".join(words)


def _read_number(token: str, ctx: str) -> str:
    """Spoken form of one numeric token (may have thousands commas, a decimal part, a percent sign)."""
    percent = token.endswith("%")
    body = token.rstrip("%").replace(",", "")
    whole, _, frac = body.partition(".")
    if ctx == "ko":
        out = ko_number(whole)
        if frac:
            out += "점" + "".join(_SINO_DIGITS[int(d)] for d in frac)
        return out + ("퍼센트" if percent else "")
    out = en_number(whole)
    if frac:
        out += " point " + " ".join(_EN_ONES[int(d)] for d in frac)
    return f" {out}{' percent' if percent else ''} "


def normalize_text(
    text: str,
    lang: str = "auto",
    user_map: Mapping[str, str] | None = None,
) -> tuple[str, list[str]]:
    """Return (spoken-form text, tokens that could not be read).

    Numbers in Japanese context cannot be read in M1 and are reported as unsupported.
    """
    if lang not in ("auto", "ko", "en", "ja"):
        raise ValueError(f"lang must be one of 'auto', 'ko', 'en', 'ja', got {lang!r}")
    if user_map:
        for key in sorted(user_map, key=len, reverse=True):
            text = text.replace(key, user_map[key])
    unsupported: list[str] = []
    out_parts: list[str] = []
    # Walk sentence by sentence so each sentence picks its own language context.
    sentences = _split_keep(text)
    for sentence in sentences:
        ctx = context_of(sentence, lang)

        def num(m: re.Match[str], ctx: str = ctx) -> str:
            if ctx == "ja":
                unsupported.append(m.group(0))
                return " "
            return _read_number(m.group(0), ctx)

        def acr(m: re.Match[str], ctx: str = ctx) -> str:
            table = _KO_LETTERS if ctx == "ko" else _EN_LETTERS
            if ctx == "ko":
                return "".join(table[c] for c in m.group(0))  # 티티에스: one word
            return " " + " ".join(table[c] for c in m.group(0)) + " "

        sentence = _NUMBER.sub(num, sentence)
        sentence = _ACRONYM.sub(acr, sentence)
        out_parts.append(sentence)
    return re.sub(r"[ \t]+", " ", "".join(out_parts)).strip(), unsupported


def _split_keep(text: str) -> list[str]:
    """Split into sentences but keep the separators so the text can be re-joined unchanged."""
    pieces: list[str] = []
    last = 0
    for m in _SENTENCE_SPLIT.finditer(text):
        pieces.append(text[last:m.end()])
        last = m.end()
    pieces.append(text[last:])
    return pieces
