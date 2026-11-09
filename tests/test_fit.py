import json

import pytest

from tts_pace import MockEngine, UnsupportedTextError, fit, fit_audio, measure

EN = ("Today we learn how to match the speaking rate of a synthetic voice. "
      "It is a short lesson about pace and silence.")
KO = ("오늘은 말하기 속도를 맞추는 방법을 알아봅니다. "
      "목표 속도에 가깝게 음성을 다시 만들고 마지막에 조금만 다듬습니다.")

KW = {"tempo_backend": "numpy", "measure_backend": "numpy", "cache_dir": False}


def test_far_target_resynthesizes_then_tempo():
    engine = MockEngine("en")
    r = fit(EN, 4.0, engine, **KW)
    assert r.route == "resynth+tempo"
    resynth = next(c for c in r.candidates if c.kind == "resynth")
    assert 3.0 < resynth.err_pct < 10.0  # the knob under-reacts, like real Piper
    assert r.best.err_pct < 1.0
    assert len(engine.calls) == 2
    assert not r.warnings


def test_near_target_is_tempo_only_with_one_engine_call():
    engine = MockEngine("en")
    base = fit(EN, 4.6, MockEngine("en"), **KW).base.measurement.sps
    r = fit(EN, base * 1.06, engine, **KW)
    assert r.route == "tempo-only"
    assert len(engine.calls) == 1
    assert r.best.err_pct < 1.5
    assert r.best.tempo == pytest.approx(1.06, abs=0.01)


def test_knob_floor_is_reported_not_hidden():
    r = fit(KO, 4.0, MockEngine("ko"), **KW)
    assert "tempo_clamped" in r.warnings
    assert "knob_response_weak" in r.warnings
    assert 2.0 <= r.best.err_pct <= 8.0
    rep = r.report()
    best = rep["candidates"][rep["best"]]
    assert best["speed"] == pytest.approx(0.74, abs=0.02) and best["tempo"] == 0.85
    assert rep["mock"] is True and rep["advice"]


def test_engine_without_knob_uses_tempo_only_and_warns_when_far():
    from tts_pace import CallableEngine

    inner = MockEngine("en")
    engine = CallableEngine(lambda t, s: inner.synthesize(t, 1.0), has_speed_knob=False)
    r = fit(EN, 3.0, engine, **KW)
    assert r.route == "tempo-only" and "tempo_clamped" in r.warnings


def test_speed_outside_engine_range_warns_knob_clamped():
    engine = MockEngine("en", speed_range=(0.95, 1.5))
    r = fit(EN, 4.0, engine, **KW)
    assert "knob_clamped" in r.warnings
    assert engine.calls[-1] == 0.95


def test_writes_files(tmp_path):
    r = fit(EN, 4.0, MockEngine("en"), out=tmp_path / "o.wav", keep_candidates=True, **KW)
    assert r.best.path == str(tmp_path / "o.wav")
    assert (tmp_path / "o_base.wav").exists() and (tmp_path / "o_resynth.wav").exists()
    assert measure(r.best.path, text=EN).sps == pytest.approx(4.0, rel=0.02)
    r.save_report(tmp_path / "r.json")
    assert json.loads((tmp_path / "r.json").read_text())["route"] == "resynth+tempo"


def test_fit_audio_tempo_only(tmp_path):
    base = MockEngine("en").synthesize(EN, 1.0)
    r = fit_audio(base, EN, 4.8, out=tmp_path / "t.wav", tempo_backend="numpy", measure_backend="numpy")
    assert r.route == "tempo-only" and r.best.err_pct < 1.5 and r.base.measurement.sps < 4.8


def test_bad_arguments():
    engine = MockEngine("en")
    with pytest.raises(ValueError, match="target_sps"):
        fit(EN, 0, engine, **KW)
    with pytest.raises(ValueError, match="tolerance"):
        fit(EN, 4.0, engine, tolerance=2, **KW)
    with pytest.raises(UnsupportedTextError):
        fit("...", 4.0, engine, **KW)
    assert engine.calls == []  # validation happens before any synthesis
