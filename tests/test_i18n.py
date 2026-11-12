"""Screen language: message tables, language choice, localized errors, layout, and the CLI end to end."""

import json
import re
import subprocess
import sys
import threading
from pathlib import Path

import numpy as np
import pytest

from tts_pace import (
    AudioClip,
    BusyError,
    EngineError,
    Limiter,
    MeasurementError,
    UnsupportedTextError,
    count_syllables,
    fit,
    measure,
    retime,
)
from tts_pace.cli import main
from tts_pace.demo import format_table, run_demo
from tts_pace.errors import TtsPaceError
from tts_pace.i18n import (
    ARGPARSE_KO,
    MESSAGES,
    display_width,
    fix_josa,
    pad,
    render_error,
    resolve_lang,
    t,
)
from tts_pace.runtime import run_command

SRC = Path(__file__).resolve().parent.parent / "src" / "tts_pace"
EN_TEXT = "Today we learn how to match the speaking rate of a synthetic voice."
KO_TEXT = "오늘은 말하기 속도를 맞추는 방법을 알아봅니다."
FIELD = re.compile(r"\{([a-z_]+)(?:[!:][^}]*)?\}")


# --- message tables -------------------------------------------------------------------------


def test_both_languages_have_the_same_keys():
    assert set(MESSAGES["en"]) == set(MESSAGES["ko"])


def test_placeholders_match_between_languages():
    for key, en in MESSAGES["en"].items():
        assert set(FIELD.findall(en.replace("{{", "").replace("}}", ""))) == set(
            FIELD.findall(MESSAGES["ko"][key].replace("{{", "").replace("}}", ""))
        ), key


def test_argparse_templates_keep_their_placeholders():
    pct = re.compile(r"%(?:\(\w+\))?[sr]")
    for en, ko in ARGPARSE_KO.items():
        assert pct.findall(en) == pct.findall(ko), en


def test_every_error_code_used_in_the_source_has_messages():
    used = set()
    for path in SRC.rglob("*.py"):
        used |= set(re.findall(r'code="([a-z_]+)"', path.read_text(encoding="utf-8")))
        used |= set(re.findall(r'code="[a-z_]+" if not unsupported else "([a-z_]+)"', path.read_text(encoding="utf-8")))
    assert used and used <= set(MESSAGES["en"]), used - set(MESSAGES["en"])


def test_korean_messages_use_the_polite_formal_style_and_no_stray_english_sentences():
    for key in ("description", "advice_tempo_clamped", "text_missing", "busy", "say_macos_only"):
        assert re.search(r"(니다|십시오)\.$", MESSAGES["ko"][key]), key


# --- language choice ------------------------------------------------------------------------


def test_resolve_lang_priority_flag_then_env_chain():
    env = {"TTS_PACE_LANG": "en", "LC_ALL": "ko_KR.UTF-8", "LC_MESSAGES": "en_US", "LANG": "en_US"}
    assert resolve_lang("ko", env) == "ko"  # flag beats everything
    assert resolve_lang(None, env) == "en"  # TTS_PACE_LANG beats LC_ALL
    del env["TTS_PACE_LANG"]
    assert resolve_lang(None, env) == "ko"  # LC_ALL beats LC_MESSAGES and LANG
    del env["LC_ALL"]
    assert resolve_lang(None, env) == "en"  # LC_MESSAGES beats LANG
    assert resolve_lang(None, {"LC_MESSAGES": "ko_KR", "LANG": "en_US"}) == "ko"
    assert resolve_lang(None, {"LANG": "ko_KR.UTF-8"}) == "ko"


def test_resolve_lang_defaults_to_english():
    assert resolve_lang(None, {}) == "en"
    assert resolve_lang(None, {"LANG": "fr_FR.UTF-8"}) == "en"
    assert resolve_lang(None, {"TTS_PACE_LANG": "", "LANG": "ko_KR"}) == "ko"  # empty = not set
    assert resolve_lang("fr", {"LANG": "ko_KR"}) == "en"  # an explicit non-Korean value means English


def test_t_falls_back_to_the_environment_language(monkeypatch):
    monkeypatch.setenv("TTS_PACE_LANG", "ko")
    assert t("label_cache") == "캐시"
    assert t("label_cache", lang="en") == "cache"


@pytest.mark.parametrize("text,expected", [
    ("파일을(를)", "파일을"), ("서버을(를)", "서버를"), ("엔진이(가)", "엔진이"), ("소리이(가)", "소리가"),
    ("경로은(는)", "경로는"), ("길이은(는)", "길이는"), ("음성와(과)", "음성과"), ("공(으)로", "공으로"),
    ("바(으)로", "바로"), ("piper이(가)", "piper이(가)"),
])
def test_fix_josa_picks_the_particle_from_the_last_character(text, expected):
    assert fix_josa(text) == expected


# --- layout ---------------------------------------------------------------------------------


def test_display_width_counts_hangul_as_two_columns():
    assert display_width("abc") == 3
    assert display_width("최적") == 4
    assert pad("최적", 9) == "최적" + " " * 5
    assert pad("7", 4, ">") == "   7"


def test_demo_table_columns_line_up_in_korean(tmp_path):
    results, _ = run_demo(tmp_path / "demo")
    lines = format_table(results, "ko").splitlines()
    head, rows = lines[0], lines[2:]
    assert display_width(lines[1]) == display_width(head)
    head_prefix = display_width(head[: -len("경고")])
    for line, (_, r) in zip(rows, results):
        warn = ", ".join(r.warnings) or "-"
        assert display_width(line[: len(line) - len(warn)]) == head_prefix


def test_demo_table_in_english_is_unchanged_by_the_layout_helper(tmp_path):
    results, _ = run_demo(tmp_path / "demo")
    head = format_table(results, "en").splitlines()[0]
    assert head == "case      base sps  route          final sps target     err  warnings"


# --- localized exceptions -------------------------------------------------------------------


def _raised():
    """Coded exceptions raised by the library, each with the code it should carry."""
    silent = AudioClip(np.zeros(22050, np.float32), 22050)
    clip = AudioClip(np.ones(22050, np.float32) * 0.1, 22050)
    cases = []

    def grab(code, fn):
        try:
            fn()
        except (TtsPaceError, ValueError) as exc:
            assert getattr(exc, "code", None) == code, (code, exc)
            cases.append(exc)
        else:
            raise AssertionError(f"{code} did not raise")

    grab("silent_clip", lambda: measure(silent))
    grab("unsupported_text", lambda: count_syllables("!!!"))
    grab("unsupported_text_detail", lambda: count_syllables("漢"))
    grab("audio_not_found", lambda: AudioClip.from_wav("/no/such/file.wav"))
    grab("tempo_factor_range", lambda: retime(clip, 2.0))
    grab("tempo_range_bad", lambda: retime(clip, 1.0, tempo_range=(2.0, 3.0)))
    grab("engine_not_found", lambda: run_command(["/no/such/tool-xyz"]))
    grab("engine_exit", lambda: run_command([sys.executable, "-c", "import sys; sys.exit(3)"]))
    grab("target_both", lambda: fit("hello", 4.0, _noop_engine(), target_duration=3.0, cache_dir=False))
    grab("target_none", lambda: fit("hello", None, _noop_engine(), cache_dir=False))
    grab("target_sps_bad", lambda: fit("hello", -1.0, _noop_engine(), cache_dir=False))
    grab("target_duration_bad", lambda: fit("hello", None, _noop_engine(), target_duration=0, cache_dir=False))
    grab("tolerance_bad", lambda: fit("hello", 4.0, _noop_engine(), tolerance=2.0, cache_dir=False))
    grab("backend_bad", lambda: measure(clip, backend="x"))
    grab("text_and_syllables", lambda: measure(clip, text="a", syllables=1))
    grab("min_silence_bad", lambda: measure(clip, min_silence=0))
    grab("silence_db_bad", lambda: measure(clip, silence_db=3))
    return cases


def _noop_engine():
    from tts_pace import MockEngine

    return MockEngine("en")


def test_english_rendering_equals_the_exception_text():
    for exc in _raised():
        assert render_error(exc, "en") == str(exc), exc.code


def test_korean_rendering_differs_and_has_no_leftover_placeholders():
    for exc in _raised():
        ko = render_error(exc, "ko")
        assert ko != str(exc) and re.search("[가-힣]", ko), exc.code
        assert not re.search(r"\{[a-z_]+\}", ko), exc.code


def test_busy_and_timeout_codes_render_in_both_languages():
    lim = Limiter(max_concurrent=1, max_waiting=0)
    started, release = threading.Event(), threading.Event()

    def hold():
        with lim.slot():
            started.set()
            release.wait(5)

    th = threading.Thread(target=hold)
    th.start()
    try:
        started.wait(5)
        with pytest.raises(BusyError) as info, lim.slot():
            pass
    finally:
        release.set()
        th.join()
    assert render_error(info.value, "en") == str(info.value)
    assert "슬롯 1개" in render_error(info.value, "ko")
    with pytest.raises(EngineError) as slow:
        run_command([sys.executable, "-c", "import time; time.sleep(5)"], timeout=0.2)
    assert render_error(slow.value, "en") == str(slow.value)
    assert "0.2초" in render_error(slow.value, "ko")


def test_exceptions_without_a_code_keep_their_own_text_and_signature():
    exc = MeasurementError("plain")
    assert str(exc) == "plain" and exc.code is None and exc.params == {}
    assert render_error(exc, "ko") == "plain"
    assert isinstance(UnsupportedTextError("x"), TtsPaceError)
    assert render_error(ValueError("odd"), "ko") == "odd"


# --- CLI end to end -------------------------------------------------------------------------


def test_flag_before_the_command_switches_the_screen_language(capsys):
    assert main(["--lang", "ko", "count", "hello"]) == 0
    out = capsys.readouterr().out
    assert "발음 형태" in out and "음절 수" in out and "spoken form" not in out


def test_count_lang_after_the_command_still_means_text_language(capsys):
    assert main(["count", "--lang", "ko", "123"]) == 0  # screen stays English (TTS_PACE_LANG=en)
    out = capsys.readouterr().out
    assert "spoken form : 백이십삼" in out  # text language ko: digits read in Korean
    assert main(["count", "--lang", "en", "123"]) == 0
    assert "spoken form : one hundred twenty three" in capsys.readouterr().out


def test_both_language_options_together(capsys):
    assert main(["--lang", "ko", "count", "--lang", "en", "hello"]) == 0
    out = capsys.readouterr().out
    assert "발음 형태" in out and "'en': 2" in out


def test_fit_lang_after_the_command_is_still_the_mock_preset(tmp_path, capsys):
    out_wav = tmp_path / "o.wav"
    assert main(["--lang", "ko", "fit", "--lang", "en", "--text", EN_TEXT, "--target", "4", "-o", str(out_wav),
                 "--no-cache"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("[mock] 연습용 목(mock) 엔진입니다") and "캐시      미스" in out and out_wav.exists()


def test_environment_variables_choose_the_language(monkeypatch, capsys):
    monkeypatch.delenv("TTS_PACE_LANG")
    monkeypatch.setenv("LANG", "ko_KR.UTF-8")
    assert main(["count", "hello"]) == 0
    assert "발음 형태" in capsys.readouterr().out
    monkeypatch.setenv("TTS_PACE_LANG", "en")  # beats LANG
    assert main(["count", "hello"]) == 0
    assert "spoken form" in capsys.readouterr().out
    assert main(["--lang", "ko", "count", "hello"]) == 0  # flag beats TTS_PACE_LANG
    assert "발음 형태" in capsys.readouterr().out


def test_json_output_is_byte_identical_in_both_languages(tmp_path, capsys):
    argv = ["fit", "--text", KO_TEXT, "--target", "5", "-o", str(tmp_path / "o.wav"), "--no-cache", "--json"]
    assert main(argv) == 0
    en = capsys.readouterr()
    assert main(["--lang", "ko", *argv]) == 0
    ko = capsys.readouterr()
    assert en.out == ko.out and json.loads(ko.out)["advice"] is not None
    assert main(["--lang", "ko", "count", "hello", "--json"]) == 0
    assert capsys.readouterr().out == json.dumps(count_syllables("hello").to_dict(), ensure_ascii=False) + "\n"


def test_korean_fit_output_has_no_english_labels(tmp_path, capsys):
    argv = ["--lang", "ko", "fit", "--text", KO_TEXT, "--target", "4", "-o", str(tmp_path / "o.wav"),
            "--no-cache", "--report", str(tmp_path / "r.json")]
    assert main(argv) == 0
    cap = capsys.readouterr()
    for word in ("base ", "best ", "speed", "tempo ", "sps", "err ", "cache ", "wrote", "warning:", "report "):
        assert word not in cap.out + cap.err, word
    assert "경고: tempo_clamped - " in cap.err or "경고: knob_response_weak - " in cap.err
    assert (tmp_path / "r.json").exists()


def test_korean_warning_text_but_english_report(tmp_path, capsys):
    report = tmp_path / "r.json"
    assert main(["--lang", "ko", "fit", "--text", KO_TEXT, "--target", "4", "-o", str(tmp_path / "o.wav"),
                 "--no-cache", "--report", str(report)]) == 0
    capsys.readouterr()
    advice = json.loads(report.read_text(encoding="utf-8"))["advice"]
    assert advice and all(not re.search("[가-힣]", a) for a in advice)


def test_korean_measure_output(tmp_path, capsys):
    from tts_pace import MockEngine

    wav = MockEngine("en").synthesize(EN_TEXT, 1.0).to_wav(tmp_path / "in.wav")
    assert main(["--lang", "ko", "measure", str(wav), "--text", EN_TEXT]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].startswith("전체 ") and "무음" in lines[0] and "발화" in lines[0]
    assert "순수 발화 기준 초당" in lines[1]


def test_korean_demo_banner_table_and_footer(tmp_path, capsys):
    assert main(["--lang", "ko", "demo", "--out", str(tmp_path / "d")]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith("[mock] 연습용 목(mock) 엔진입니다") and "사례" in out[1]
    assert "에 저장했습니다" in out[-1]
    assert (tmp_path / "d" / "report.json").exists()


def test_korean_runtime_errors_exit_2(tmp_path, capsys):
    assert main(["--lang", "ko", "measure", str(tmp_path / "missing.wav")]) == 2
    cap = capsys.readouterr()
    assert cap.out == "" and cap.err.startswith("오류: 오디오 파일을 찾을 수 없습니다")
    assert main(["--lang", "ko", "fit", "--text", "hello", "--target", "-1", "-o", str(tmp_path / "o.wav")]) == 2
    assert "오류: target_sps 는 0보다 커야 합니다" in capsys.readouterr().err
    assert main(["--lang", "ko", "fit", "--text-file", str(tmp_path / "nope.txt"), "--target", "4",
                 "-o", str(tmp_path / "o.wav")]) == 2
    assert "파일을 읽을 수 없습니다" in capsys.readouterr().err
    blocker = tmp_path / "plain-file"
    blocker.write_text("x")  # a file where a folder is needed: writing below it fails
    assert main(["--lang", "ko", "fit", "--text", "hello", "--target", "4", "-o", str(blocker / "o.wav"),
                 "--no-cache"]) == 2
    err = capsys.readouterr().err
    assert "오류: 쓸 수 없는 경로입니다" in err and "-o 로" in err


def test_english_runtime_errors_are_unchanged(tmp_path, capsys):
    assert main(["measure", str(tmp_path / "missing.wav")]) == 2
    assert capsys.readouterr().err.startswith("error: Audio file not found: ")


def test_korean_argparse_errors_exit_2(capsys):
    with pytest.raises(SystemExit) as e:
        main(["--lang", "ko", "fit", "--target", "4", "-o", "x"])
    assert e.value.code == 2
    err = capsys.readouterr().err
    assert "사용법:" in err and "오류: 다음 인자 중 하나가 필요합니다" in err and "usage:" not in err
    with pytest.raises(SystemExit) as e:
        main(["--lang", "ko", "bogus"])
    assert e.value.code == 2
    err = capsys.readouterr().err
    assert "오류:" in err and "잘못된 선택입니다" in err
    with pytest.raises(SystemExit) as e:
        main(["--lang", "ko"])
    assert e.value.code == 2 and "다음 인자가 필요합니다" in capsys.readouterr().err
    with pytest.raises(SystemExit) as e:
        main(["--lang", "fr", "count", "x"])  # not a screen language: rejected, and still exit 2
    assert e.value.code == 2 and "usage:" in capsys.readouterr().err


def test_english_argparse_errors_are_unchanged(capsys):
    with pytest.raises(SystemExit) as e:
        main(["fit", "--target", "4", "-o", "x"])
    assert e.value.code == 2
    err = capsys.readouterr().err
    assert "usage:" in err and "error: one of the arguments --text --text-file is required" in err


def test_korean_help_covers_every_option(capsys):
    for argv in (["--lang", "ko", "--help"], ["--lang", "ko", "count", "--help"],
                 ["--lang", "ko", "measure", "--help"], ["--lang", "ko", "retime", "--help"],
                 ["--lang", "ko", "fit", "--help"], ["--lang", "ko", "demo", "--help"]):
        with pytest.raises(SystemExit) as e:
            main(argv)
        assert e.value.code == 0
        out = capsys.readouterr().out
        assert "사용법:" in out and "옵션:" in out and "show this help" not in out
        assert not re.search(r"^\s+--?[\w-]+.*\s(the|show|print|write|file|target|output|result)\s", out, re.M), out


def test_argparse_patch_is_removed_after_main(capsys):
    import argparse

    before = argparse._
    main(["--lang", "ko", "count", "x"])
    capsys.readouterr()
    assert argparse._ is before


def test_module_entry_point_honours_the_flag():
    proc = subprocess.run([sys.executable, "-m", "tts_pace.cli", "--lang", "ko", "count", "hi"],
                          capture_output=True, text=True, check=False)
    assert proc.returncode == 0 and "발음 형태" in proc.stdout


# --- regressions: non-UTF-8 script files, nested engine reasons, duplicate Python warning ---------


@pytest.mark.parametrize("lang,needle", [("en", "UTF-8"), ("ko", "UTF-8 로 다시 저장")])
def test_non_utf8_text_file_gets_a_localized_fix_hint(tmp_path, capsys, lang, needle):
    bad = tmp_path / "bad.txt"
    bad.write_bytes(b"\xff\xfe\x00bad")
    from tts_pace import MockEngine

    wav =tmp_path / "a.wav"
    MockEngine("en").synthesize("hello there", 1.0).to_wav(wav)
    assert main(["--lang", lang, "measure", str(wav), "--text-file", str(bad)]) == 2
    err = capsys.readouterr().err
    assert needle in err and "codec" not in err and str(bad) in err


@pytest.mark.parametrize("lang,needle,absent", [("ko", "오디오 프레임이 없습니다", "no audio frames"),
                                                ("en", "no audio frames", "프레임")])
def test_say_reason_is_rendered_in_the_screen_language(tmp_path, capsys, monkeypatch, lang, needle, absent):
    import wave

    import tts_pace.cli as cli_mod
    from tts_pace import SayEngine

    def runner(argv, timeout=None, input_text=None):
        with wave.open(argv[argv.index("-o") + 1], "wb") as w:  # a WAV with zero frames
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(cli_mod, "SayEngine", lambda voice=None: SayEngine(voice, runner=runner))
    argv = ["--lang", lang, "fit", "--engine", "say", "--text", "안녕", "--target", "4",
            "-o", str(tmp_path / "s.wav"), "--no-cache"]
    assert main(argv) == 2
    err = capsys.readouterr().err
    assert needle in err and absent not in err


def test_cli_hides_the_english_python_warning_but_keeps_the_localized_lines(capsys):
    import warnings

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert main(["--lang", "ko", "count", "안녕 漢字"]) == 0
    assert not [w for w in caught if "Unsupported" in w.category.__name__]
    assert "미지원" in capsys.readouterr().out


def test_library_still_emits_the_unsupported_warning():
    from tts_pace import UnsupportedCharsWarning

    with pytest.warns(UnsupportedCharsWarning):
        count_syllables("안녕 漢字")
