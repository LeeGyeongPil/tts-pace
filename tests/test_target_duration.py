"""Total-length target (target_duration): synthetic audio, numpy backend, no network or ffmpeg."""

import json
import math

import pytest

from tts_pace import MockEngine, fit, fit_audio, measure
from tts_pace.audio import AudioClip
from tts_pace.cli import main

from conftest import SR

TEXT = "가" * 20  # 20 syllables, matches the 20 bursts of speech_fixture
KW = {"tempo_backend": "numpy", "measure_backend": "numpy"}
EN = ("Today we learn how to match the speaking rate of a synthetic voice. "
      "It is a short lesson about pace and silence.")


def _total(clip) -> float:
    return measure(clip, syllables=20, backend="numpy").total_s


@pytest.mark.parametrize("ratio", [0.90, 1.10])
def test_fit_audio_hits_total_length_inside_tempo_range(speech_fixture, ratio):
    clip = AudioClip(speech_fixture, SR)
    t = _total(clip) * ratio
    r = fit_audio(clip, TEXT, None, target_duration=t, **KW)
    assert r.route == "tempo-only" and not r.warnings
    assert abs(r.best.measurement.total_s - t) / t <= 0.01
    assert r.length_err_pct <= 1.0


def test_target_far_outside_range_is_clamped_not_an_error(speech_fixture):
    clip = AudioClip(speech_fixture, SR)
    t = _total(clip) * 0.70
    r = fit_audio(clip, TEXT, None, target_duration=t, **KW)
    assert "tempo_clamped" in r.warnings
    assert r.length_err_pct > 1


def test_fit_with_mock_engine_length_mode():
    engine = MockEngine("en")
    base_total = fit(EN, 4.6, MockEngine("en"), cache_dir=False, **KW).base.measurement.total_s
    t = base_total * 1.08
    r = fit(EN, None, engine, target_duration=t, cache_dir=False, **KW)
    assert r.route in {"tempo-only", "resynth+tempo", "resynth"}
    assert len(engine.calls) in (1, 2)
    assert r.length_err_pct <= 2.0 or "tempo_clamped" in r.warnings


@pytest.mark.parametrize("bad", [0, -1, math.nan, math.inf])
def test_bad_duration_is_value_error_before_any_engine_call(bad):
    engine = MockEngine("en")
    with pytest.raises(ValueError, match="target_duration must be a positive number of seconds"):
        fit(EN, None, engine, target_duration=bad, cache_dir=False, **KW)
    assert engine.calls == []


def test_both_or_neither_target_is_value_error(speech_fixture):
    clip = AudioClip(speech_fixture, SR)
    with pytest.raises(ValueError, match="either target_sps or target_duration, not both"):
        fit_audio(clip, TEXT, 5.0, target_duration=4.0, **KW)
    with pytest.raises(ValueError, match=r"give target_sps \(syllables/second\) or target_duration \(seconds\)"):
        fit_audio(clip, TEXT, None, **KW)


def test_report_has_length_fields_and_roundtrips(speech_fixture, tmp_path):
    clip = AudioClip(speech_fixture, SR)
    t = _total(clip) * 0.9
    r = fit_audio(clip, TEXT, None, target_duration=t, **KW)
    rep = r.report()
    assert rep["target_duration"] == t
    assert rep["result_total_s"] == pytest.approx(r.best.measurement.total_s, abs=1e-3)
    assert "length_err_pct" in rep and rep["target_sps"] > 0
    back = type(r).from_report(json.loads(r.save_report(tmp_path / "r.json").read_text()))
    assert back.target_duration == t and back.length_err_pct == pytest.approx(r.length_err_pct, abs=1e-3)


# ---- CLI ----

def _wav(tmp_path, speech_fixture):
    p = tmp_path / "in.wav"
    AudioClip(speech_fixture, SR).to_wav(p)
    return p


def test_cli_conflicting_or_missing_or_zero_target_exit_2(tmp_path, capsys):
    base = ["fit", "--text", EN, "-o", str(tmp_path / "o.wav"), "--no-cache"]
    for extra, msg in ((["--target", "4", "--target-duration", "4"], "not allowed with argument"),
                       ([], "one of the arguments --target --target-duration is required")):
        with pytest.raises(SystemExit) as e:
            main(base + extra)
        assert e.value.code == 2 and msg in capsys.readouterr().err
    assert main(base + ["--target-duration", "0"]) == 2
    assert "target_duration must be a positive number" in capsys.readouterr().err
    with pytest.raises(SystemExit) as e:
        main(["retime", str(tmp_path / "x.wav"), "--text", EN, "-o", "o.wav"])
    assert e.value.code == 2


def test_cli_retime_prints_length_line(tmp_path, speech_fixture, capsys):
    wav = _wav(tmp_path, speech_fixture)
    t = _total(AudioClip(speech_fixture, SR)) * 0.9
    assert main(["retime", str(wav), "--text", TEXT, "--target-duration", f"{t:.3f}", "-o", str(tmp_path / "o.wav")]) == 0
    out = capsys.readouterr().out
    assert f"s (target {t:.2f}s, err " in out and "\nlength    " in out


def test_cli_fit_length_mode_json_report(tmp_path, capsys):
    rpt = tmp_path / "r.json"
    code = main(["fit", "--text", EN, "--target-duration", "4", "-o", str(tmp_path / "o.wav"),
                 "--no-cache", "--report", str(rpt)])
    assert code == 0
    out = capsys.readouterr().out
    assert "length    " in out and "(target 4.00s" in out
    assert json.loads(rpt.read_text())["target_duration"] == 4.0


# ---- unchanged behaviour when the option is not used ----

SPS_KEYS = {"version", "engine", "mock", "mock_note", "target_sps", "syllables", "first_ratio", "route", "best",
            "candidates", "warnings", "advice", "cache_hit", "cache_key"}


def test_sps_mode_report_keys_and_cli_output_unchanged(tmp_path, speech_fixture, capsys):
    r = fit(EN, 4.0, MockEngine("en"), cache_dir=False, **KW)
    assert set(r.report()) == SPS_KEYS
    wav = _wav(tmp_path, speech_fixture)
    assert main(["retime", str(wav), "--text", TEXT, "--target", "5", "-o", str(tmp_path / "o.wav")]) == 0
    assert main(["fit", "--text", EN, "--target", "4", "-o", str(tmp_path / "f.wav"), "--no-cache"]) == 0
    assert "length" not in capsys.readouterr().out.replace("wrote", "")


def test_sps_mode_cache_key_is_byte_identical_to_v0_1_1(tmp_path):
    # Key computed with the code before target_duration existed (v0.1.1).
    r = fit("Today we learn how to match the speaking rate.", 4.0, MockEngine("en"), cache_dir=tmp_path, **KW)
    assert r.cache_key == "bd7efbb866268414f06ac297e6a33d8d668fea4f7ce8f2c8ac1e2f9b64160f8c"  # gitleaks:allow (sha256 cache key, not a secret)


def test_length_mode_cache_key_differs_and_hits(tmp_path):
    a = fit(EN, None, MockEngine("en"), target_duration=4.0, cache_dir=tmp_path, **KW)
    b = fit(EN, None, MockEngine("en"), target_duration=4.0, cache_dir=tmp_path, **KW)
    c = fit(EN, None, MockEngine("en"), target_duration=5.0, cache_dir=tmp_path, **KW)
    assert not a.cache_hit and b.cache_hit and a.cache_key != c.cache_key
    assert b.target_duration == 4.0


# ---- resynth+tempo path (re-synthesis changes the pauses, so tempo must aim at the real total length) ----

@pytest.mark.parametrize("ratio", [0.80, 0.90, 1.20])
def test_length_mode_resynth_plus_tempo_hits_length_inside_tempo_range(ratio):
    base_total = fit(EN, 4.6, MockEngine("en"), cache_dir=False, **KW).base.measurement.total_s
    t = base_total * ratio
    engine = MockEngine("en")
    r = fit(EN, None, engine, target_duration=t, cache_dir=False, **KW)
    assert r.route == "resynth+tempo"          # the path really taken (not tempo-only)
    assert len(engine.calls) == 2              # base synthesis + one re-synthesis
    assert not r.warnings                      # target is inside the tempo range
    assert r.best.kind == "resynth+tempo"
    # Asserted directly, not replaced by a warning.
    assert abs(r.best.measurement.total_s - t) / t <= 0.01
    assert r.length_err_pct <= 1.0
    # The best candidate must be the one closest in length, not just in speech rate.
    errs = {c.kind: abs(c.measurement.total_s - t) for c in r.candidates}
    assert errs[r.best.kind] == min(errs.values())


KO = "오늘은 합성 음성의 말하기 속도를 맞추는 방법을 배웁니다. 쉼과 속도에 관한 짧은 수업입니다."


@pytest.mark.parametrize("ratio", [0.80, 0.90])
def test_length_mode_best_is_picked_by_length_error_not_speech_rate(ratio):
    # With the Korean mock preset, re-synthesis alone is closest in speech rate to the converted target,
    # yet only the final resynth+tempo clip matches the requested total length.
    base_total = fit(KO, 4.6, MockEngine("ko"), cache_dir=False, **KW).base.measurement.total_s
    t = base_total * ratio
    r = fit(KO, None, MockEngine("ko"), target_duration=t, cache_dir=False, **KW)
    by_rate = min(r.candidates, key=lambda c: c.err_pct)
    assert by_rate.kind == "resynth"           # a rate-based choice would pick this one
    assert r.route == "resynth+tempo" and r.best.kind == "resynth+tempo" and not r.warnings
    assert abs(r.best.measurement.total_s - t) / t <= 0.01
    assert r.length_err_pct <= 1.0
