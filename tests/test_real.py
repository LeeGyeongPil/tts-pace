"""Tests that need real tools on this machine. Deselected by default (`-m "not real"`).

Run them with: uv run pytest -q -m real
"""

import shutil
import sys

import pytest

from tts_pace import SayEngine, fit, measure, retime
from tts_pace.runtime import find_ffmpeg

pytestmark = pytest.mark.real


@pytest.mark.skipif(sys.platform != "darwin" or shutil.which("say") is None, reason="needs macOS say")
def test_say_engine_fits_a_korean_sentence(tmp_path):
    r = fit("오늘은 말하기 속도를 맞추는 방법을 알아봅니다.", 5.0, SayEngine("Yuna"), out=tmp_path / "o.wav",
            cache_dir=False)
    assert r.best.err_pct < 10 and (tmp_path / "o.wav").exists()


@pytest.mark.skipif(find_ffmpeg() is None, reason="needs ffmpeg")
def test_ffmpeg_atempo_matches_the_requested_factor(tmp_path):
    from tts_pace import MockEngine

    clip = MockEngine("en").synthesize("Today we learn how to match the speaking rate.", 1.0)
    out = retime(clip, 1.1, backend="ffmpeg")
    assert measure(out, syllables=10).net_s == pytest.approx(measure(clip, syllables=10).net_s / 1.1, rel=0.03)
