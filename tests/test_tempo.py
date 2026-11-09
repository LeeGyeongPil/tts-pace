import numpy as np
import pytest
from conftest import SR

from tts_pace import AudioClip, measure, retime
from tts_pace.tempo import wsola


def dominant_hz(x: np.ndarray) -> float:
    spec = np.abs(np.fft.rfft(x * np.hanning(len(x))))
    return float(np.argmax(spec) * SR / len(x))


@pytest.mark.parametrize("factor", [0.85, 1.15])
def test_speech_time_scales_and_pitch_is_kept(speech_fixture, factor):
    clip = AudioClip(speech_fixture, SR)
    before = measure(clip, syllables=20)
    out = retime(clip, factor, backend="numpy")
    after = measure(out, syllables=20)
    assert after.net_s == pytest.approx(before.net_s / factor, rel=0.02)
    f0 = dominant_hz(clip.samples)
    assert abs(dominant_hz(out.samples) - f0) / f0 <= 0.03


def test_output_length_is_exact():
    x = np.sin(2 * np.pi * 200 * np.arange(SR * 2) / SR).astype(np.float32)
    assert len(wsola(x, SR, 1.1)) == round(len(x) / 1.1)


def test_out_of_range_raises_and_clamp_applies(speech_fixture):
    clip = AudioClip(speech_fixture, SR)
    with pytest.raises(ValueError, match="allowed tempo range"):
        retime(clip, 0.8, backend="numpy")
    out = retime(clip, 0.8, backend="numpy", clamp=True)
    assert out.duration == pytest.approx(clip.duration / 0.85, rel=0.001)


def test_custom_range_and_bad_values(speech_fixture):
    clip = AudioClip(speech_fixture, SR)
    out = retime(clip, 0.8, backend="numpy", tempo_range=(0.75, 1.25))
    assert out.duration == pytest.approx(clip.duration / 0.8, rel=0.001)
    for bad in (0, -1, float("nan")):
        with pytest.raises(ValueError):
            retime(clip, bad, backend="numpy")
    with pytest.raises(ValueError, match="tempo_range"):
        retime(clip, 1.0, tempo_range=(1.2, 1.1))


def test_factor_one_is_identity_and_writes_file(tmp_path, speech_fixture):
    clip = AudioClip(speech_fixture, SR)
    out = retime(clip, 1.0, out=tmp_path / "x.wav", backend="numpy")
    assert out is clip and (tmp_path / "x.wav").exists()
