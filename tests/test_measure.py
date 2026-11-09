import pytest
from conftest import SR, silence

from tts_pace import AudioClip, MeasurementError, measure
from tts_pace.runtime import find_ffmpeg


def test_silence_is_removed_but_short_pause_is_kept(speech_fixture):
    m = measure(AudioClip(speech_fixture, SR), syllables=20, backend="numpy")
    assert m.silence_s == pytest.approx(1.6, abs=0.03)
    assert m.gaps == 2  # the 0.4 s pause is shorter than min_silence
    assert m.sps == pytest.approx(20 / m.net_s, rel=0.01)
    assert m.net_s == pytest.approx(m.total_s - m.silence_s)


def test_text_counts_syllables(speech_fixture):
    m = measure(AudioClip(speech_fixture, SR), text="오늘은 말하기 속도를", backend="numpy")
    assert m.syllables == 9 and m.sps == pytest.approx(9 / m.net_s)


def test_all_silent_raises():
    with pytest.raises(MeasurementError, match="no speech"):
        measure(AudioClip(silence(2.0), SR), syllables=5)


def test_rate_is_none_without_text(speech_fixture):
    assert measure(AudioClip(speech_fixture, SR)).sps is None


def test_bad_arguments(speech_fixture):
    clip = AudioClip(speech_fixture, SR)
    with pytest.raises(ValueError, match="either text or syllables"):
        measure(clip, text="a", syllables=1)
    with pytest.raises(ValueError, match="backend"):
        measure(clip, backend="sox")
    with pytest.raises(ValueError, match="negative"):
        measure(clip, silence_db=10)


def test_wav_roundtrip(tmp_path, speech_fixture):
    path = AudioClip(speech_fixture, SR).to_wav(tmp_path / "a.wav")
    assert measure(path, syllables=20).gaps == 2


def test_missing_file_has_clear_error(tmp_path):
    from tts_pace import AudioFormatError

    with pytest.raises(AudioFormatError, match="not found"):
        measure(tmp_path / "nope.wav")


@pytest.mark.skipif(find_ffmpeg() is None, reason="ffmpeg not installed")
def test_ffmpeg_backend_agrees_with_numpy(speech_fixture):
    clip = AudioClip(speech_fixture, SR)
    a = measure(clip, syllables=20, backend="numpy")
    b = measure(clip, syllables=20, backend="ffmpeg")
    assert abs(a.silence_s - b.silence_s) <= 0.05
    assert a.gaps == b.gaps
