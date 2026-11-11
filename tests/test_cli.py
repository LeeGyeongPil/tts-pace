import json
import runpy
from pathlib import Path

from tts_pace.cli import main

ROOT = Path(__file__).resolve().parent.parent
EN = "Today we learn how to match the speaking rate of a synthetic voice."


def test_demo_prints_mock_banner_table_and_report(tmp_path, capsys):
    assert main(["demo", "--out", str(tmp_path / "demo")]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].startswith("[mock]")
    rows = {ln.split("  ")[0].strip(): ln for ln in lines if ln.startswith(("en ", "ko "))}
    assert len(rows) == 4
    assert "tempo_clamped" in rows["ko floor"]
    far_err = float(rows["en far"].split("%")[0].split()[-1])
    assert far_err < 1.0
    report = json.loads((tmp_path / "demo" / "report.json").read_text())
    assert report["mock"] is True and len(report["cases"]) == 4


def test_quickstart_prints_one_line(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    runpy.run_path(str(ROOT / "examples" / "quickstart.py"), run_name="__main__")
    out = capsys.readouterr().out.strip().splitlines()
    assert len(out) == 1 and out[0].startswith("path=") and " err=" in out[0]


def make_wav(tmp_path, preset="en", text=EN):
    from tts_pace import MockEngine

    return MockEngine(preset).synthesize(text, 1.0).to_wav(tmp_path / "in.wav")


def test_measure_json(tmp_path, capsys):
    wav = make_wav(tmp_path)
    assert main(["measure", str(wav), "--text", EN, "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["syllables"] == 17 and 4.0 < data["sps"] < 5.2 and data["gaps"] >= 1


def test_retime_json_has_sps_and_tempo(tmp_path, capsys):
    wav = make_wav(tmp_path)
    assert main(["retime", str(wav), "--text", EN, "--target", "4.9", "-o", str(tmp_path / "o.wav"), "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    best = data["candidates"][data["best"]]
    assert best["tempo"] > 1 and abs(best["measurement"]["sps"] - 4.9) / 4.9 < 0.015
    assert (tmp_path / "o.wav").exists()


def test_retime_at_the_limit_exits_zero_with_warning(tmp_path, capsys):
    wav = make_wav(tmp_path)
    code = main(["retime", str(wav), "--text", EN, "--target", "9", "-o", str(tmp_path / "o.wav"), "--json"])
    cap = capsys.readouterr()
    assert code == 0
    assert "tempo_clamped" in json.loads(cap.out)["warnings"] and "tempo_clamped" in cap.err


def test_fit_cache_hit_on_second_run(tmp_path, capsys):
    args = ["fit", "--engine", "mock", "--text", EN, "--target", "4.0", "-o", str(tmp_path / "o.wav"),
            "--cache-dir", str(tmp_path / "c"), "--report", str(tmp_path / "r.json")]
    assert main(args) == 0
    first = capsys.readouterr().out
    assert first.startswith("[mock]") and "cache     miss" in first
    assert main(args) == 0
    assert "cache     hit" in capsys.readouterr().out


def test_count_command(capsys):
    assert main(["count", "2026년 TTS 속도"]) == 0
    assert "이천이십육년 티티에스 속도" in capsys.readouterr().out


def test_errors_are_short_messages_with_exit_code_2(tmp_path, capsys):
    assert main(["measure", str(tmp_path / "missing.wav")]) == 2
    assert "error:" in capsys.readouterr().err
    assert main(["count", "..."]) == 2


def test_unwritable_output_path_is_a_short_error_not_a_traceback(tmp_path, capsys):
    wav = make_wav(tmp_path)
    blocker = tmp_path / "blocker"
    blocker.write_text("a file, so it cannot be a folder")
    bad = blocker / "x.wav"
    assert main(["retime", str(wav), "--text", EN, "--target", "4", "-o", str(bad)]) == 2
    err = capsys.readouterr().err
    assert err.startswith("error: cannot write") and "-o" in err and "Traceback" not in err


def test_non_audio_file_error_says_how_to_fix(tmp_path, capsys):
    from tts_pace.runtime import find_ffmpeg

    junk = tmp_path / "notes.txt"
    junk.write_text("hello, not audio")
    assert main(["measure", str(junk), "--text", "hello"]) == 2
    err = capsys.readouterr().err
    assert err.startswith("error:") and "16-bit WAV" in err
    assert find_ffmpeg() is None or "not an audio file ffmpeg can read" in err


# --- fit --json -------------------------------------------------------------------------------

ROUTES = {"base", "tempo-only", "resynth", "resynth+tempo"}


def fit_args(tmp_path, *extra):
    return ["fit", "--engine", "mock", "--text", EN, "-o", str(tmp_path / "o.wav"), "--no-cache", *extra]


def test_fit_json_sps_mode_stdout_is_one_json_and_banner_goes_to_stderr(tmp_path, capsys):
    assert main(fit_args(tmp_path, "--target", "4.0", "--json")) == 0
    cap = capsys.readouterr()
    assert "[mock]" not in cap.out and cap.out.count("\n") == 1
    assert "[mock]" in cap.err
    data = json.loads(cap.out)
    assert data["version"] == 1 and data["mock"] is True and isinstance(data["mock_note"], str)
    assert data["target_sps"] == 4.0 and data["route"] in ROUTES
    assert isinstance(data["best"], int) and isinstance(data["cache_hit"], bool)
    assert isinstance(data["warnings"], list) and isinstance(data["advice"], list)
    cand = data["candidates"][data["best"]]
    assert abs(cand["measurement"]["sps"] - 4.0) < 0.3 and isinstance(cand["err_pct"], float)
    assert isinstance(cand["speed"], float) and isinstance(cand["tempo"], float)
    assert "target_duration" not in data and "result_total_s" not in data


def test_fit_json_target_duration_mode(tmp_path, capsys):
    assert main(fit_args(tmp_path, "--target-duration", "6", "--json")) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["target_duration"] == 6.0
    assert isinstance(data["result_total_s"], float) and 0 < data["result_total_s"] < 20
    assert isinstance(data["length_err_pct"], float) and 0 <= data["length_err_pct"] < 100
    assert data["route"] in ROUTES


def test_fit_json_warning_branch_keeps_exit_0_and_stderr_warning(tmp_path, capsys):
    assert main(fit_args(tmp_path, "--target", "9", "--json")) == 0
    cap = capsys.readouterr()
    data = json.loads(cap.out)
    assert "tempo_clamped" in data["warnings"] and "warning: tempo_clamped" in cap.err
    assert data["route"] != "base"


def test_fit_json_cache_branch(tmp_path, capsys):
    args = fit_args(tmp_path, "--target", "4.0", "--json")
    args.remove("--no-cache")
    args += ["--cache-dir", str(tmp_path / "c")]
    assert main(args) == 0
    first = json.loads(capsys.readouterr().out)
    assert main(args) == 0
    second = json.loads(capsys.readouterr().out)
    assert first["cache_hit"] is False and second["cache_hit"] is True
    assert isinstance(second["cache_key"], str)


def test_fit_json_with_report_file_matches_stdout(tmp_path, capsys):
    rep = tmp_path / "r.json"
    assert main(fit_args(tmp_path, "--target", "4.0", "--json", "--report", str(rep))) == 0
    out = capsys.readouterr().out
    assert json.loads(out) == json.loads(rep.read_text(encoding="utf-8"))


def test_fit_json_error_branch_leaves_stdout_empty(tmp_path, capsys):
    assert main(["fit", "--engine", "mock", "--text", "", "--target", "4", "-o", str(tmp_path / "o.wav"),
                 "--no-cache", "--json"]) == 2
    cap = capsys.readouterr()
    assert cap.out == "" and "error:" in cap.err
    assert main(fit_args(tmp_path, "--target-duration", "0", "--json")) == 2
    cap = capsys.readouterr()
    assert cap.out == "" and "error:" in cap.err


def test_fit_help_lists_json(capsys):
    import pytest

    with pytest.raises(SystemExit):
        main(["fit", "--help"])
    assert "--json" in capsys.readouterr().out


def test_fit_without_json_output_lines_unchanged(tmp_path, capsys):
    assert main(fit_args(tmp_path, "--target", "4.0")) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].startswith("[mock]")
    assert [ln.split()[0] for ln in lines[1:2]] == ["base"]
    assert [ln.split()[0] for ln in lines if ln.startswith(("best", "cache", "wrote"))] == ["best", "cache", "wrote"]
    assert not any(ln.startswith(("length", "report")) for ln in lines)
    assert main(fit_args(tmp_path, "--target-duration", "6")) == 0
    lines = capsys.readouterr().out.splitlines()
    assert [ln.split()[0] for ln in lines if ln.startswith(("best", "length", "cache", "wrote"))] == [
        "best", "length", "cache", "wrote"]
