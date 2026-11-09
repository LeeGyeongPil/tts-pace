import subprocess
from pathlib import Path

import pytest

from tts_pace import AudioClip, CallableEngine, EngineError, MockEngine, PiperEngine, SayEngine

CLIP = MockEngine("en").synthesize("hello there", 1.0)


def fake_runner(calls):
    """Pretends to be the engine program: records argv and writes a WAV where it was told to."""

    def run(argv, timeout=None, input_text=None):
        calls.append((list(argv), input_text, timeout))
        out = argv[argv.index("-o") + 1] if "-o" in argv else argv[argv.index("-f") + 1]
        CLIP.to_wav(out)
        return subprocess.CompletedProcess(argv, 0, "", "")

    return run


def test_piper_command_forces_determinism_and_length_scale():
    engine = PiperEngine("/voices/a.onnx")
    built = engine.build_command(1.25, Path("/tmp/o.wav"))
    argv = built.argv
    assert argv[argv.index("--noise-scale") + 1] == "0"
    assert argv[argv.index("--noise-w-scale") + 1] == "0"
    assert argv[argv.index("--length-scale") + 1] == f"{1 / 1.25:.4f}"
    assert not built.clamped and engine.info.deterministic


def test_piper_runs_through_injected_runner_and_sends_text_on_stdin():
    calls = []
    clip = PiperEngine("/voices/a.onnx", runner=fake_runner(calls)).synthesize("hello", 1.0)
    assert isinstance(clip, AudioClip) and calls[0][1] == "hello"


def test_piper_needs_a_voice(monkeypatch):
    monkeypatch.delenv("TTS_PACE_PIPER_VOICE", raising=False)
    with pytest.raises(ValueError, match="TTS_PACE_PIPER_VOICE"):
        PiperEngine()
    monkeypatch.setenv("TTS_PACE_PIPER_VOICE", "/v/x.onnx")
    assert PiperEngine().voice == "/v/x.onnx"


def test_say_rate_is_base_wpm_times_speed():
    engine = SayEngine("Yuna")
    built = engine.build_command(1.2, Path("o.wav"), Path("t.txt"))
    assert built.argv[:3] == ["say", "-v", "Yuna"]
    assert built.argv[built.argv.index("-r") + 1] == str(round(175 * 1.2))
    assert not built.clamped


def test_say_clamps_out_of_range_and_says_so():
    engine = SayEngine("Yuna")
    low = engine.build_command(0.5, Path("o.wav"), Path("t.txt"))
    assert low.clamped and low.applied_speed == 0.86
    assert low.argv[low.argv.index("-r") + 1] == str(round(175 * 0.86))
    assert engine.build_command(9.0, Path("o.wav"), Path("t.txt")).applied_speed == 1.6


def test_say_synthesize_with_fake_runner():
    calls = []
    SayEngine(runner=fake_runner(calls)).synthesize("안녕하세요", 1.0)
    argv = calls[0][0]
    assert "-v" not in argv and "--file-format=WAVE" in argv


def test_callable_passes_speed_through_unchanged():
    seen = []

    def tts(text, speed):
        seen.append(speed)
        return CLIP

    engine = CallableEngine(tts, speed_range=(0.7, 2.0), deterministic=True, cache_id="my:voice")
    engine.synthesize("x", 1.37)
    assert seen == [1.37] and engine.info.cache_id == "my:voice" and engine.info.deterministic


def test_callable_accepts_tuple_and_path(tmp_path):
    wav = CLIP.to_wav(tmp_path / "a.wav")
    assert CallableEngine(lambda t, s: str(wav)).synthesize("x", 1).sample_rate == CLIP.sample_rate
    assert len(CallableEngine(lambda t, s: (CLIP.samples, CLIP.sample_rate)).synthesize("x", 1).samples) > 0


def test_callable_validation_and_bad_return():
    with pytest.raises(ValueError, match="cache_id"):
        CallableEngine(lambda t, s: CLIP, deterministic=True)
    with pytest.raises(ValueError, match="speed_range"):
        CallableEngine(lambda t, s: CLIP, speed_range=(2.0, 1.0))
    with pytest.raises(TypeError):
        CallableEngine("not callable")  # type: ignore[arg-type]
    with pytest.raises(EngineError, match="must return"):
        CallableEngine(lambda t, s: 42).synthesize("x", 1)  # type: ignore[arg-type,return-value]


def test_mock_engine_behaviours():
    ko = MockEngine("ko")
    assert ko.rate_for(0.5) == ko.rate_for(0.9)  # silent floor: below 0.9 nothing changes
    en = MockEngine("en")
    assert en.rate_for(2.0) / en.rate_for(1.0) == pytest.approx(2 ** 0.6)  # not proportional
    assert MockEngine("en", jitter=0.1).info.deterministic is False
    a, b = (MockEngine("en", jitter=0.1).synthesize("one two three four", 1.0) for _ in range(2))
    assert len(a.samples) != len(b.samples) or not (a.samples == b.samples).all()
