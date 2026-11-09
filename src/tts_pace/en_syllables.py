"""English syllable estimate: vowel-group heuristic plus a small exception dictionary.

This is an approximation (see README, limits). The exception dictionary below is
hand-written (< 300 words) and was NOT extracted from the evaluation fixture.
"""

from __future__ import annotations

import re

# Words the rules get wrong that are common in narration, plus spelled-out letter names
# (used for acronyms like "TTS" -> "tee tee ess").
EXCEPTIONS: dict[str, int] = {
    # letter names used when acronyms are spelled out
    "ay": 1, "bee": 1, "see": 1, "dee": 1, "ee": 1, "eff": 1, "jee": 1, "aitch": 1,
    "eye": 1, "jay": 1, "kay": 1, "ell": 1, "em": 1, "en": 1, "oh": 1, "pee": 1,
    "cue": 1, "ar": 1, "ess": 1, "tee": 1, "you": 1, "vee": 1, "ex": 1, "why": 1, "zee": 1,
    # numbers and very common irregular words
    "one": 1, "two": 1, "three": 1, "four": 1, "five": 1, "six": 1, "seven": 2, "eight": 1,
    "nine": 1, "ten": 1, "eleven": 3, "twelve": 1, "thirteen": 2, "fourteen": 2, "fifteen": 2,
    "sixteen": 2, "seventeen": 3, "eighteen": 2, "nineteen": 2, "twenty": 2, "thirty": 2,
    "forty": 2, "fifty": 2, "sixty": 2, "seventy": 3, "eighty": 2, "ninety": 2, "hundred": 2,
    "thousand": 2, "million": 2, "billion": 2, "zero": 2, "point": 1, "percent": 2,
    "the": 1, "a": 1, "i": 1, "area": 3, "idea": 3, "real": 1, "really": 2, "being": 2,
    "doing": 2, "going": 2, "seeing": 2, "people": 2, "business": 2, "every": 2, "everyone": 3,
    "everything": 3, "different": 3, "interesting": 3, "favorite": 3, "comfortable": 3,
    "vegetable": 3, "camera": 3, "family": 3, "chocolate": 3, "evening": 2, "usually": 3,
    "actually": 4, "especially": 4, "beautiful": 3, "science": 2, "scientist": 3, "quiet": 2,
    "poem": 2, "poet": 2, "create": 2, "creating": 3, "creative": 3, "video": 3, "audio": 3,
    "radio": 3, "studio": 3, "ratio": 3, "piano": 3, "violin": 3, "diet": 2, "client": 2,
    "giant": 2, "lion": 2, "iron": 2, "fire": 1, "hour": 1, "our": 1, "flower": 2, "power": 2,
    "tower": 2, "shower": 2, "wear": 1, "where": 1, "there": 1, "were": 1, "here": 1,
    "queue": 1, "league": 1, "tongue": 1, "ocean": 2, "island": 2, "stomach": 2, "orange": 2,
    "average": 3, "aware": 2, "someone": 2, "anyone": 3, "anything": 3, "something": 2,
    "nothing": 2, "everybody": 4, "somebody": 3, "anybody": 4, "nobody": 3, "maybe": 2,
    "already": 3, "also": 2, "always": 2, "again": 2, "against": 2, "because": 2, "before": 2,
    "between": 2, "become": 2, "behind": 2, "below": 2, "beyond": 2, "world": 1, "word": 1,
    "work": 1, "year": 1, "years": 1, "your": 1, "yours": 1, "speech": 1, "speaking": 2,
    "rate": 1, "speed": 1, "pace": 1, "tempo": 2, "pitch": 1, "voice": 1, "voices": 2,
    "engine": 2, "engines": 3, "synthesize": 3, "synthesis": 3, "syllable": 3, "syllables": 3,
    "measure": 2, "measures": 2, "measured": 2, "text": 1, "texts": 1, "narration": 3,
    "tutorial": 4, "lesson": 2, "learn": 1, "learning": 2, "listen": 2, "listening": 3,
    "language": 3, "english": 2, "korean": 3, "japanese": 3, "welcome": 2, "today": 2,
    "tomorrow": 3, "yesterday": 3, "morning": 2, "night": 1, "hello": 2, "thanks": 1,
    "okay": 2, "ok": 2, "yes": 1, "no": 1, "quick": 1, "quickly": 2, "slow": 1, "slowly": 2,
    "fast": 1, "faster": 2, "slower": 2, "target": 2, "closer": 2, "close": 1, "closed": 1,
    "loop": 1, "result": 2, "results": 2, "silence": 2, "silent": 2, "pause": 1, "pauses": 2,
    "sentence": 2, "sentences": 3, "word": 1, "words": 1, "minute": 2, "minutes": 2,
    "second": 2, "seconds": 2, "average": 3, "per": 1, "per-second": 3, "over": 2, "under": 2,
    "using": 2, "used": 1, "uses": 2, "use": 1, "make": 1, "makes": 1, "made": 1, "making": 2,
    "take": 1, "takes": 1, "taken": 2, "give": 1, "gives": 1, "given": 2, "have": 1, "has": 1,
    "are": 1, "is": 1, "was": 1, "be": 1, "been": 1, "to": 1, "of": 1, "and": 1, "or": 1,
    "in": 1, "on": 1, "at": 1, "it": 1, "its": 1, "this": 1, "that": 1, "these": 2, "those": 1,
}

_VOWELS = "aeiouy"
# ti/ci/si before a vowel sound make a "sh" consonant (nation, social, passion).
_SH = re.compile(r"(?:[tcs]i)(?=o|a[ln]|ou|en)")
# Vowel pairs that are normally two syllables (create, radio, duo).
_HIATUS = ("ia", "io", "iu", "eo", "ua", "uo", "ii", "ao")


def count_en_word(word: str) -> int:
    """Estimate the syllable count of one English word (letters and apostrophes only)."""
    w = re.sub(r"[^a-z]", "", word.lower())
    if not w:
        return 0
    if w in EXCEPTIONS:
        return EXCEPTIONS[w]
    return max(_heuristic(w), 1)


def _heuristic(w: str) -> int:
    s = w
    s = s.replace("qu", "q")  # u after q is a consonant glide
    s = re.sub(r"gu(?=[aeiy])", "g", s)
    if s.startswith("y") and len(s) > 1 and s[1] in _VOWELS:
        s = "j" + s[1:]  # initial y is a consonant (yes, young)
    s = _SH.sub("sh", s)
    # Silent endings: -e (but not consonant+le), -es, -ed.
    if re.search(r"[^aeiouy]le$", s):
        pass  # table, little: "le" is a syllable
    elif re.search(r"(?:sh|ch|[sxzcg])es$", s):
        pass  # boxes, watches: "es" is pronounced
    elif re.search(r"[^aeiouy]es$", s) and len(s) > 3:
        s = s[:-2]
    elif re.search(r"[td]ed$", s):
        pass  # wanted, needed
    elif re.search(r"[^aeiouy]ed$", s) and len(s) > 3:
        s = s[:-2]
    elif re.search(r"[^aeiouy]e$", s) and len(s) > 2:
        s = s[:-1]
    groups = re.findall(r"[aeiouy]+", s)
    count = len(groups)
    for g in groups:
        for pair in _HIATUS:
            if pair in g:
                count += 1
    return count
