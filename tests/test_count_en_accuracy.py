from pathlib import Path

from tts_pace.en_syllables import EXCEPTIONS, count_en_word

FIXTURE = Path(__file__).parent / "fixtures" / "cmudict_sample.tsv"


def _rows() -> list[tuple[str, int]]:
    return [(w, int(n)) for w, n in (line.split("\t") for line in FIXTURE.read_text().splitlines())]


def test_sample_size():
    assert len(_rows()) == 2000


def test_heuristic_beats_syllables_baseline():
    rows = [(w, n) for w, n in _rows() if w not in EXCEPTIONS]
    hits = sum(count_en_word(w) == n for w, n in rows)
    accuracy = hits / len(rows)
    print(f"\nEnglish word-level accuracy on {len(rows)} CMUdict words: {accuracy:.4f}")
    assert accuracy >= 0.80  # the `syllables` package scored 0.7847 on the same kind of sample


def test_exception_words_match_exactly():
    sample = dict(_rows())
    for w in EXCEPTIONS:
        if w in sample:
            assert count_en_word(w) == sample[w], w  # dictionary agrees with CMUdict where both exist
    for w, n in EXCEPTIONS.items():
        assert count_en_word(w) == n
