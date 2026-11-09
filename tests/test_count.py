import pytest

from tts_pace import UnsupportedCharsWarning, UnsupportedTextError, count_syllables
from tts_pace.normalize import ko_number


def test_korean_blocks():
    assert count_syllables("오늘은 말하기 속도를").total == 9


def test_korean_number_is_read_sino_korean():
    c = count_syllables("2026년")
    assert c.normalized_text == "이천이십육년"
    assert c.total == 6


def test_acronym_depends_on_language_context():
    ko = count_syllables("한국어 TTS")
    assert "티티에스" in ko.normalized_text
    assert count_syllables("TTS").total == 3  # tee-tee-ess in English context
    assert count_syllables("티티에스").total == 4
    assert count_syllables("TTS", lang="ko").total == 4  # explicit language wins
    assert count_syllables("한국어 TTS").total == 3 + 4


def test_japanese_morae():
    assert count_syllables("きょうは").total == 3
    assert count_syllables("ちょっと").total == 3  # ちょ + っ + と
    assert count_syllables("ラーメン").by_script["ja"] == 4  # ra, long vowel, me, n


def test_kanji_is_recorded_and_warns():
    with pytest.warns(UnsupportedCharsWarning):
        c = count_syllables("今日は")
    assert c.unsupported == ("今", "日")
    assert c.total == 1


def test_no_countable_syllables_raises():
    with pytest.raises(UnsupportedTextError):
        count_syllables("!!! ??? ...")
    with pytest.raises(UnsupportedTextError, match="unsupported: 漢, 字"):
        count_syllables("漢字")


def test_english_numbers_and_percent():
    c = count_syllables("3.5% of 1,234 people")
    assert "three point five percent" in c.normalized_text
    assert "one thousand two hundred thirty four" in c.normalized_text


def test_user_dictionary_hook():
    assert count_syllables("in 2026", normalize={"2026": "twenty twenty six"}).total == 1 + 2 + 2 + 1


def test_bad_arguments():
    with pytest.raises(ValueError, match="lang"):
        count_syllables("hi", lang="xx")
    with pytest.raises(TypeError):
        count_syllables(123)  # type: ignore[arg-type]


def test_sino_korean_edge_cases():
    assert ko_number("10000") == "만"
    assert ko_number("0") == "영"
    assert ko_number("110") == "백십"
    assert ko_number("100000000") == "억"
