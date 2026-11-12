"""Screen language (English / Korean) for the command line: messages, selection and layout helpers.

All human-readable CLI text lives in ``MESSAGES`` below, one table per language. Machine output
(``--json``, ``report.json``), exit codes and the library's exception messages stay English.

Language choice, first match wins: ``--lang en|ko`` (before the command) > ``TTS_PACE_LANG`` >
``LC_ALL`` > ``LC_MESSAGES`` > ``LANG``. A value starting with ``ko`` means Korean; anything else,
or nothing, means English.
"""

from __future__ import annotations

import os
import re
import unicodedata
from collections.abc import Mapping
from typing import Any

LANGS = ("en", "ko")
ENV_VAR = "TTS_PACE_LANG"
_ENV_ORDER = (ENV_VAR, "LC_ALL", "LC_MESSAGES", "LANG")


def _pick(value: str | None) -> str | None:
    """Map one setting to 'ko'/'en'. Empty means 'not set' (None); anything but ko... means English."""
    if value is None or not value.strip():
        return None
    return "ko" if value.strip().lower().startswith("ko") else "en"


def resolve_lang(cli_value: str | None = None, env: Mapping[str, str] | None = None) -> str:
    """Return 'en' or 'ko' following the priority described in the module docstring."""
    env = os.environ if env is None else env
    for value in (cli_value, *(env.get(name) for name in _ENV_ORDER)):
        lang = _pick(value)
        if lang is not None:
            return lang
    return "en"


# --- messages ---------------------------------------------------------------------------------
# Placeholders use str.format syntax ({name}). Both languages must use the same names.
# Korean sentences end in the formal polite style; particles after placeholders use the
# "(이)가"-style markers that fix_josa() resolves from the last character.

_EN: dict[str, str] = {
    # help
    "description": "Measure and fit TTS speaking rate (syllables/second).",
    "help_lang": "screen language for messages and help: en or ko. Give it before the command "
                 "(tts-pace --lang ko fit ...); the --lang after count/fit means something else. "
                 "Default: TTS_PACE_LANG, then LC_ALL / LC_MESSAGES / LANG.",
    "help_demo": "run four fits with the practice (mock) engine",
    "help_demo_out": "output folder (default: ./tts-pace-demo)",
    "help_count": "show the spoken form and syllable count of a text",
    "help_count_lang": "text language (default: auto)",
    "help_json_count": "print the result as JSON",
    "help_measure": "measure a WAV file",
    "help_json_measure": "print the measurement as JSON",
    "help_retime": "change an existing recording's tempo toward a target rate (0.85-1.15 limit)",
    "help_json_retime": "print the report JSON to stdout",
    "help_fit": "synthesize with an engine and fit to a target rate",
    "help_text": "the spoken text",
    "help_text_file": "file containing the spoken text (UTF-8)",
    "help_target": "target syllables per second",
    "help_target_duration": "target total length in seconds, pauses included",
    "help_voice": "say voice name, or Piper .onnx path",
    "help_fit_lang": "mock engine preset (default: guessed from the text)",
    "help_cache_dir": "result cache folder (default: {path})",
    "help_no_cache": "do not read or write the result cache",
    "help_report": "write the report JSON here",
    "help_json_fit": "print the report JSON to stdout (notices go to stderr)",
    # output labels
    "label_base": "base",
    "label_best": "best",
    "label_length": "length",
    "label_cache": "cache",
    "label_wrote": "wrote",
    "label_report": "report",
    "label_spoken": "spoken form",
    "label_syllables": "syllables",
    "label_unsupported": "unsupported",
    "cache_hit": "hit",
    "cache_miss": "miss",
    "unit_sps": "sps",
    "kind_base": "base",
    "kind_tempo-only": "tempo-only",
    "kind_resynth": "resynth",
    "kind_resynth+tempo": "resynth+tempo",
    "candidate": "speed x{speed:.3f}  tempo x{tempo:.3f}  -> {sps:.2f} sps  err {err:.2f}%",
    "base_value": "{sps:.2f} sps",
    "best_value": "{route}: {sps:.2f} sps (target {target:g}, err {err:.2f}%)",
    "length_value": "{total:.2f}s (target {target:.2f}s, err {err:.2f}%)",
    "measure_line1": "total {total:.2f}s  silence {silence:.2f}s ({gaps} gaps)  speech {net:.2f}s",
    "measure_line2": "{syllables} syllables -> {sps:.2f} syllables/second of pure speech",
    "demo_wrote": "wrote {out}/ (WAV files + report.json: {report})",
    "mock_banner": "[mock] practice (mock) engine - not a real TTS",
    # demo table
    "col_case": "case",
    "col_base_sps": "base sps",
    "col_route": "route",
    "col_final_sps": "final sps",
    "col_target": "target",
    "col_err": "err",
    "col_warnings": "warnings",
    # warnings and errors
    "warning_prefix": "warning",
    "error_prefix": "error",
    "advice_knob_response_weak": "The engine speed knob changed the pace much less than asked (it may stop at a "
                                 "floor or scale non-linearly). Try another voice or engine setting, or edit the text.",
    "advice_knob_clamped": "The requested engine speed was outside the engine's range and was cut to it.",
    "advice_tempo_clamped": "The tempo change hit its limit, so the target was not reached. Shorten or lengthen "
                            "the text, or choose an engine setting closer to the target pace.",
    "advice_unsupported_chars": "Some characters were not counted (for example kanji); give a spoken form with "
                                "normalize={...} for accurate rates.",
    "text_missing": "Give the script with --text TEXT or --text-file FILE.",
    "text_file_unreadable": "Cannot read --text-file {path}: {reason}",
    "text_file_not_utf8": "--text-file {path} is not valid UTF-8 text. Re-save the file as UTF-8 and try again.",
    "output_path_default": "the output path",
    "cannot_write": "cannot write {target}: {reason}. Choose a writable folder with -o.",
    # library errors (identical to the English exception messages)
    "busy": "All {slots} slot(s) are busy and {waiting} request(s) are already waiting. "
            "Retry later or raise Limiter(max_waiting=...).",
    "engine_timeout": "{name} did not finish within {timeout:g}s. Real engines can be slow on a busy "
                      "machine: raise the timeout or try a shorter text.",
    "engine_not_found": "{name} was not found. Install it or give its full path.",
    "engine_start_failed": "{name} could not be started: {reason}",
    "engine_exit": "{name} exited with code {returncode}: {tail}",
    "unsupported_text": "No countable syllables found in the text. Provide Hangul, kana or Latin letters, "
                        "or map the text to a spoken form with normalize={{...}}.",
    "unsupported_text_detail": "No countable syllables found in the text (unsupported: {unsupported}). "
                               "Provide Hangul, kana or Latin letters, or map the text to a spoken form "
                               "with normalize={{...}}.",
    "ffmpeg_backend_missing": "backend='ffmpeg' needs ffmpeg. Install it, set TTS_PACE_FFMPEG, "
                              "or use backend='numpy'.",
    "silent_clip": "The clip has no speech: everything is silence at the chosen threshold "
                   "({silence_db} dB, min {min_silence}s). Check the file, or lower silence_db "
                   "(for example -50) if the recording has a noise floor.",
    "audio_not_found": "Audio file not found: {path}",
    "audio_no_frames": "{path} has no audio frames.",
    "audio_bad_width": "Unsupported sample width {width} bytes in {path}.",
    "audio_no_ffmpeg": "{path} is not a PCM WAV file and ffmpeg was not found to decode it. "
                       "Convert it to 16-bit WAV, or install ffmpeg (or set TTS_PACE_FFMPEG).",
    "audio_ffmpeg_unreadable": "{path} is not an audio file ffmpeg can read; convert it to 16-bit WAV. "
                               "(ffmpeg said: {reason})",
    "piper_no_output": "Piper finished but wrote no audio file. Check the voice path and the piper install.",
    "piper_voice_needed": "PiperEngine needs a voice .onnx file: pass voice=... or set TTS_PACE_PIPER_VOICE. "
                          "Download one with: python -m piper.download_voices en_US-lessac-medium",
    "say_macos_only": "SayEngine only works on macOS. Use CallableEngine for other platforms.",
    "say_no_audio": "say wrote no audio ({reason}). Check the voice name (`say -v '?'`) and that the "
                    "process is allowed to use macOS speech synthesis (some sandboxes block it).",
    "callable_bad_return": "The function given to CallableEngine must return an AudioClip, a WAV path or "
                           "(samples, sample_rate); it returned {type}.",
    "target_both": "give either target_sps or target_duration, not both",
    "target_none": "give target_sps (syllables/second) or target_duration (seconds)",
    "target_duration_bad": "target_duration must be a positive number of seconds "
                           "(total length including pauses, e.g. 4.0), got {value!r}",
    "target_sps_bad": "target_sps must be positive (syllables per second, e.g. 5.0), got {value!r}",
    "tolerance_bad": "tolerance must be in [0, 1), e.g. 0.10 for 10%, got {value!r}",
    "tempo_range_bad": "tempo_range must satisfy 0 < low <= 1 <= high, got {value!r}",
    "backend_bad": "backend must be 'auto', 'numpy' or 'ffmpeg', got {value!r}",
    "text_and_syllables": "Give either text or syllables, not both.",
    "min_silence_bad": "min_silence must be > 0 seconds",
    "silence_db_bad": "silence_db must be negative (dBFS), e.g. -60",
    "tempo_factor_range": "factor {factor} is outside the allowed tempo range {lo}-{hi}. Large changes sound "
                          "artificial: change the text or the engine speed instead, or pass clamp=True to use "
                          "{applied}.",
}

_KO: dict[str, str] = {
    # help
    "description": "TTS 말하기 속도(초당 음절 수)를 측정하고 맞춥니다.",
    "help_lang": "메시지와 도움말의 화면 언어(en 또는 ko)입니다. 명령 앞에 지정합니다"
                 "(tts-pace --lang ko fit ...). count/fit 뒤의 --lang 은 다른 뜻입니다. "
                 "기본값: TTS_PACE_LANG, 그다음 LC_ALL / LC_MESSAGES / LANG 입니다.",
    "help_demo": "연습용 목(mock) 엔진으로 맞춤 4가지를 실행합니다",
    "help_demo_out": "출력 폴더(기본값: ./tts-pace-demo)",
    "help_count": "텍스트의 발음 형태와 음절 수를 보여 줍니다",
    "help_count_lang": "텍스트 언어(기본값: auto)",
    "help_json_count": "결과를 JSON 으로 출력합니다",
    "help_measure": "WAV 파일의 말하기 속도를 측정합니다",
    "help_json_measure": "측정 결과를 JSON 으로 출력합니다",
    "help_retime": "기존 녹음의 템포를 목표 속도에 가깝게 바꿉니다(0.85~1.15 한도)",
    "help_json_retime": "보고서 JSON 을 표준 출력으로 내보냅니다",
    "help_fit": "엔진으로 음성을 만든 뒤 목표 속도에 맞춥니다",
    "help_text": "읽을 텍스트",
    "help_text_file": "읽을 텍스트가 담긴 파일(UTF-8)",
    "help_target": "목표 속도(초당 음절 수)",
    "help_target_duration": "휴지를 포함한 목표 전체 길이(초)",
    "help_voice": "say 음성 이름 또는 Piper .onnx 경로",
    "help_fit_lang": "목 엔진 프리셋(기본값: 텍스트로 추측)",
    "help_cache_dir": "결과 캐시 폴더(기본값: {path})",
    "help_no_cache": "결과 캐시를 읽거나 쓰지 않습니다",
    "help_report": "보고서 JSON 을 이 경로에 저장합니다",
    "help_json_fit": "보고서 JSON 을 표준 출력으로 내보냅니다(안내는 표준 오류로 나갑니다)",
    # output labels
    "label_base": "기준",
    "label_best": "최적",
    "label_length": "길이",
    "label_cache": "캐시",
    "label_wrote": "저장",
    "label_report": "보고서",
    "label_spoken": "발음 형태",
    "label_syllables": "음절 수",
    "label_unsupported": "미지원",
    "cache_hit": "적중",
    "cache_miss": "미스",
    "unit_sps": "음절/초",
    "kind_base": "기준",
    "kind_tempo-only": "템포만",
    "kind_resynth": "재합성",
    "kind_resynth+tempo": "재합성+템포",
    "candidate": "속도 x{speed:.3f}  템포 x{tempo:.3f}  -> {sps:.2f} 음절/초  오차 {err:.2f}%",
    "base_value": "{sps:.2f} 음절/초",
    "best_value": "{route}: {sps:.2f} 음절/초 (목표 {target:g}, 오차 {err:.2f}%)",
    "length_value": "{total:.2f}초 (목표 {target:.2f}초, 오차 {err:.2f}%)",
    "measure_line1": "전체 {total:.2f}초  무음 {silence:.2f}초 (휴지 {gaps}회)  발화 {net:.2f}초",
    "measure_line2": "음절 {syllables}개 -> 순수 발화 기준 초당 {sps:.2f} 음절",
    "demo_wrote": "{out}/ 에 저장했습니다 (WAV 파일 + report.json: {report})",
    "mock_banner": "[mock] 연습용 목(mock) 엔진입니다 - 실제 TTS 가 아닙니다",
    # demo table
    "col_case": "사례",
    "col_base_sps": "기준 속도",
    "col_route": "경로",
    "col_final_sps": "최종 속도",
    "col_target": "목표",
    "col_err": "오차",
    "col_warnings": "경고",
    # warnings and errors
    "warning_prefix": "경고",
    "error_prefix": "오류",
    "advice_knob_response_weak": "엔진 속도 조절값이 요청한 만큼 속도를 바꾸지 못했습니다(하한에서 멈추거나 비선형일 수 "
                                 "있습니다). 다른 음성이나 엔진 설정을 쓰거나 텍스트를 고쳐 보십시오.",
    "advice_knob_clamped": "요청한 엔진 속도가 엔진의 허용 범위를 벗어나 범위 안으로 잘렸습니다.",
    "advice_tempo_clamped": "템포 변경이 한도에 걸려 목표에 도달하지 못했습니다. 텍스트를 줄이거나 늘리거나, "
                            "목표 속도에 더 가까운 엔진 설정을 고르십시오.",
    "advice_unsupported_chars": "일부 문자(예: 한자)는 세지 못했습니다. 정확한 속도를 위해 normalize={...} 로 "
                                "발음 형태를 지정하십시오.",
    "text_missing": "--text 텍스트 또는 --text-file 파일로 대본을 지정하십시오.",
    "text_file_unreadable": "--text-file {path} 파일을 읽을 수 없습니다: {reason}",
    "text_file_not_utf8": "--text-file {path} 파일이 UTF-8 텍스트가 아닙니다. UTF-8 로 다시 저장한 뒤 시도하십시오.",
    "output_path_default": "출력 경로",
    "cannot_write": "쓸 수 없는 경로입니다: {target} ({reason}). -o 로 쓰기 가능한 폴더를 지정하십시오.",
    # library errors
    "busy": "슬롯 {slots}개가 모두 사용 중이고 대기 요청도 이미 {waiting}개입니다. "
            "나중에 다시 시도하거나 Limiter(max_waiting=...) 값을 늘리십시오.",
    "engine_timeout": "{name}이(가) {timeout:g}초 안에 끝나지 않았습니다. 바쁜 컴퓨터에서는 실제 엔진이 느릴 수 있으니 "
                      "제한 시간을 늘리거나 더 짧은 텍스트로 시도하십시오.",
    "engine_not_found": "{name}을(를) 찾을 수 없습니다. 설치하거나 전체 경로를 지정하십시오.",
    "engine_start_failed": "{name}을(를) 시작할 수 없습니다: {reason}",
    "engine_exit": "{name}이(가) 비정상 종료했습니다(종료 코드 {returncode}): {tail}",
    "unsupported_text": "텍스트에서 셀 수 있는 음절을 찾지 못했습니다. 한글, 가나, 라틴 문자를 넣거나 "
                        "normalize={{...}} 로 발음 형태를 지정하십시오.",
    "unsupported_text_detail": "텍스트에서 셀 수 있는 음절을 찾지 못했습니다(미지원: {unsupported}). "
                               "한글, 가나, 라틴 문자를 넣거나 normalize={{...}} 로 발음 형태를 지정하십시오.",
    "ffmpeg_backend_missing": "backend='ffmpeg' 에는 ffmpeg 가 필요합니다. 설치하거나 TTS_PACE_FFMPEG 를 "
                              "지정하거나 backend='numpy' 를 쓰십시오.",
    "silent_clip": "클립에 말소리가 없습니다. 선택한 기준({silence_db} dB, 최소 {min_silence}초)에서 전부 "
                   "무음입니다. 파일을 확인하거나, 녹음에 배경 잡음이 있다면 silence_db 를 낮추십시오(예: -50).",
    "audio_not_found": "오디오 파일을 찾을 수 없습니다: {path}",
    "audio_no_frames": "{path} 에 오디오 프레임이 없습니다.",
    "audio_bad_width": "지원하지 않는 샘플 폭 {width}바이트입니다: {path}",
    "audio_no_ffmpeg": "{path} 은(는) PCM WAV 파일이 아니고 디코딩할 ffmpeg 도 찾지 못했습니다. "
                       "16비트 WAV 로 변환하거나 ffmpeg 를 설치(또는 TTS_PACE_FFMPEG 지정)하십시오.",
    "audio_ffmpeg_unreadable": "{path} 은(는) ffmpeg 가 읽을 수 있는 오디오 파일이 아닙니다. "
                               "16비트 WAV 로 변환하십시오. (ffmpeg 응답: {reason})",
    "piper_no_output": "Piper 가 끝났지만 오디오 파일이 만들어지지 않았습니다. 음성 경로와 piper 설치를 확인하십시오.",
    "piper_voice_needed": "PiperEngine 에는 음성 .onnx 파일이 필요합니다. voice=... 를 넘기거나 "
                          "TTS_PACE_PIPER_VOICE 를 지정하십시오. 내려받기: "
                          "python -m piper.download_voices en_US-lessac-medium",
    "say_macos_only": "SayEngine 은 macOS 에서만 동작합니다. 다른 플랫폼에서는 CallableEngine 을 쓰십시오.",
    "say_no_audio": "say 가 오디오를 만들지 못했습니다({reason}). 음성 이름(`say -v '?'`)과, 프로세스에 macOS 음성 "
                    "합성 권한이 있는지 확인하십시오(일부 샌드박스는 막습니다).",
    "callable_bad_return": "CallableEngine 에 넘긴 함수는 AudioClip, WAV 경로, 또는 (samples, sample_rate) 를 "
                           "반환해야 하는데 {type} 을(를) 반환했습니다.",
    "target_both": "target_sps 와 target_duration 중 하나만 지정하십시오.",
    "target_none": "target_sps(초당 음절 수) 또는 target_duration(초)을 지정하십시오.",
    "target_duration_bad": "target_duration 은 0보다 큰 초 단위 값이어야 합니다"
                           "(휴지를 포함한 전체 길이, 예: 4.0). 받은 값: {value!r}",
    "target_sps_bad": "target_sps 는 0보다 커야 합니다(초당 음절 수, 예: 5.0). 받은 값: {value!r}",
    "tolerance_bad": "tolerance 는 [0, 1) 범위여야 합니다(예: 10%는 0.10). 받은 값: {value!r}",
    "tempo_range_bad": "tempo_range 는 0 < low <= 1 <= high 를 만족해야 합니다. 받은 값: {value!r}",
    "backend_bad": "backend 는 'auto', 'numpy', 'ffmpeg' 중 하나여야 합니다. 받은 값: {value!r}",
    "text_and_syllables": "텍스트와 음절 수 중 하나만 지정하십시오.",
    "min_silence_bad": "min_silence 는 0초보다 커야 합니다.",
    "silence_db_bad": "silence_db 는 음수(dBFS)여야 합니다(예: -60).",
    "tempo_factor_range": "배율 {factor} 이(가) 허용 템포 범위 {lo}~{hi} 를 벗어났습니다. 큰 변화는 부자연스럽게 "
                          "들립니다. 대신 텍스트나 엔진 속도를 바꾸거나, clamp=True 를 넘겨 {applied} 를 쓰십시오.",
}

MESSAGES: dict[str, dict[str, str]] = {"en": _EN, "ko": _KO}

# argparse's own fixed phrases (usage line, errors). Keyed by argparse's English template.
ARGPARSE_KO: dict[str, str] = {
    "usage: ": "사용법: ",
    "options": "옵션",
    "positional arguments": "위치 인자",
    "subcommands": "하위 명령",
    "%(heading)s:": "%(heading)s:",
    "show this help message and exit": "이 도움말을 보여 주고 종료합니다",
    "show program's version number and exit": "프로그램 버전을 보여 주고 종료합니다",
    "%(prog)s: error: %(message)s\n": "%(prog)s: 오류: %(message)s\n",
    "%(prog)s: warning: %(message)s\n": "%(prog)s: 경고: %(message)s\n",
    "the following arguments are required: %s": "다음 인자가 필요합니다: %s",
    "one of the arguments %s is required": "다음 인자 중 하나가 필요합니다: %s",
    "not allowed with argument %s": "%s 인자와 함께 쓸 수 없습니다",
    "unrecognized arguments: %s": "알 수 없는 인자입니다: %s",
    "invalid choice: %(value)r (choose from %(choices)s)": "잘못된 선택입니다: %(value)r (선택 가능: %(choices)s)",
    "unknown parser %(parser_name)r (choices: %(choices)s)": "알 수 없는 명령입니다: %(parser_name)r (선택 가능: %(choices)s)",
    "invalid %(type)s value: %(value)r": "%(type)s 값이 잘못되었습니다: %(value)r",
    "expected one argument": "인자 하나가 필요합니다",
    "expected at least one argument": "인자가 하나 이상 필요합니다",
    "expected at most one argument": "인자는 하나까지만 쓸 수 있습니다",
    "argument %(argument_name)s: %(message)s": "%(argument_name)s 인자: %(message)s",
    "ambiguous option: %(option)s could match %(matches)s": "모호한 옵션입니다: %(option)s 은(는) %(matches)s 와 일치할 수 있습니다",
    "ignored explicit argument %r": "지정한 인자 %r 은(는) 쓸 수 없습니다",
    "unexpected option string: %s": "예상하지 못한 옵션 문자열입니다: %s",
    " (default: %(default)s)": " (기본값: %(default)s)",
}


# --- lookup -----------------------------------------------------------------------------------

_JOSA = {"은(는)": ("은", "는"), "이(가)": ("이", "가"), "을(를)": ("을", "를"), "와(과)": ("과", "와")}
_JOSA_RE = re.compile(r"([가-힣])(은\(는\)|이\(가\)|을\(를\)|와\(과\)|\(으\)로)")


def fix_josa(text: str) -> str:
    """Resolve Korean particle markers such as 을(를) when the character before them is Hangul.

    After a non-Hangul character (digits, Latin) the marker is left as written, which reads fine.
    """

    def pick(m: re.Match[str]) -> str:
        syllable, marker = m.group(1), m.group(2)
        code = ord(syllable) - 0xAC00
        jong = code % 28  # 0 means no final consonant
        if marker == "(으)로":
            return syllable + ("로" if jong in (0, 8) else "으로")
        with_final, without_final = _JOSA[marker]
        return syllable + (with_final if jong else without_final)

    return _JOSA_RE.sub(pick, text)


def t(key: str, *, lang: str | None = None, **params: Any) -> str:
    """Return message ``key`` in ``lang`` (default: resolved from the environment) with params filled in."""
    lang = lang if lang in LANGS else resolve_lang()
    template = MESSAGES[lang].get(key) or MESSAGES["en"][key]
    text = template.format(**params) if params else template.replace("{{", "{").replace("}}", "}")
    return fix_josa(text) if lang == "ko" else text


def render_error(exc: BaseException, lang: str | None = None) -> str:
    """Message for an exception: translated when it carries a known ``code``, else its own text."""
    code = getattr(exc, "code", None)
    if code and code in MESSAGES["en"]:
        params = dict(getattr(exc, "params", {}))
        cause = exc.__cause__
        if "reason" in params and getattr(cause, "code", None):  # nested library error: translate it too
            params["reason"] = render_error(cause, lang)
        try:
            return t(code, lang=lang, **params)
        except (KeyError, IndexError, ValueError):  # a params/template mismatch must never hide the error
            pass
    return str(exc)


def argparse_gettext(lang: str):
    """Return a replacement for argparse's gettext function that answers in ``lang``."""
    table = ARGPARSE_KO if lang == "ko" else {}
    return lambda message: table.get(message, message)


# --- layout -----------------------------------------------------------------------------------


def display_width(text: str) -> int:
    """Terminal columns used by ``text``: wide and fullwidth characters (Hangul, CJK) take two."""
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in text)


def pad(text: str, width: int, align: str = "<") -> str:
    """Pad ``text`` with spaces to ``width`` display columns ('<' left-aligned, '>' right-aligned)."""
    gap = max(0, width - display_width(text))
    return text + " " * gap if align == "<" else " " * gap + text
