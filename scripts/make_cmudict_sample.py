"""Build the English syllable evaluation sample from a CMUdict ``cmudict.dict`` file.

Usage: python scripts/make_cmudict_sample.py CMUDICT_PATH -o OUT.tsv [--seed 7] [--n 2000]

Output lines are ``word<TAB>syllables`` where syllables is the number of vowel
phones (stress digits) of the first listed pronunciation. Only purely alphabetic
words are sampled. CMUdict is BSD-licensed; see tests/fixtures/CMUDICT-LICENSE.
"""

from __future__ import annotations

import argparse
import random
from pathlib import Path


def load_words(path: Path) -> dict[str, int]:
    words: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        word = parts[0]
        if "(" in word or not word.isalpha() or not word.isascii():
            continue  # skip alternate pronunciations ("word(2)") and non-letters
        if word in words:
            continue
        words[word] = sum(1 for ph in parts[1:] if ph[-1].isdigit())
    return words


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("cmudict", type=Path)
    ap.add_argument("-o", "--out", type=Path, required=True)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--n", type=int, default=2000)
    args = ap.parse_args()
    words = load_words(args.cmudict)
    keys = sorted(w for w, n in words.items() if n > 0)
    sample = random.Random(args.seed).sample(keys, args.n)
    args.out.write_text("".join(f"{w}\t{words[w]}\n" for w in sorted(sample)), encoding="utf-8")
    print(f"wrote {len(sample)} words to {args.out}")


if __name__ == "__main__":
    main()
