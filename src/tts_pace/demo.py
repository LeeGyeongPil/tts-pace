"""`tts-pace demo`: four fits with the practice (mock) engine, no keys or real TTS needed."""

from __future__ import annotations

import json
from pathlib import Path

from .engines.mock import MockEngine
from .fit import FitResult, fit
from .i18n import display_width, pad, t

MOCK_BANNER = "[mock] 연습용 목(mock) 엔진 — 실제 TTS 아님 (practice engine, not a real TTS)"  # both languages, kept for compatibility


def banner(lang: str = "en") -> str:
    """The practice-mode notice in one language (the CLI prints this one)."""
    return t("mock_banner", lang=lang)

EN_TEXT = ("Today we learn how to match the speaking rate of a synthetic voice. "
           "It is a short lesson about pace and silence.")
KO_TEXT = ("오늘은 말하기 속도를 맞추는 방법을 알아봅니다. "
           "목표 속도에 가깝게 음성을 다시 만들고 마지막에 조금만 다듬습니다.")

# (name, text, mock preset, target syllables/second, what it shows)
CASES = [
    ("en far", EN_TEXT, "en", 4.0, "far target: re-synthesize, then tempo"),
    ("en near", EN_TEXT, "en", 4.9, "near target: tempo only"),
    ("ko near", KO_TEXT, "ko", 5.7, "near target: tempo only"),
    ("ko floor", KO_TEXT, "ko", 4.0, "knob stops at its floor: limit shown"),
]


def run_demo(out_dir: str | Path = "tts-pace-demo") -> tuple[list[tuple[str, FitResult]], Path]:
    """Run the four cases, write WAVs and report.json, return the results."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "en.txt").write_text(EN_TEXT, encoding="utf-8")
    (out / "ko.txt").write_text(KO_TEXT, encoding="utf-8")
    results: list[tuple[str, FitResult]] = []
    for name, text, preset, target, _ in CASES:
        engine = MockEngine(preset)
        slug = name.replace(" ", "_")
        # numpy backends: same result whether or not ffmpeg is installed
        result = fit(text, target, engine, out=out / f"{slug}.wav", tempo_backend="numpy",
                     measure_backend="numpy", cache_dir=False, keep_candidates=True)
        results.append((name, result))

    report = {
        "mock": True,
        "mock_note": "practice (mock) engine, not a real TTS",
        "cases": [{"name": n, **r.report()} for n, r in results],
    }
    report_path = out / "report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return results, report_path




def format_table(results: list[tuple[str, FitResult]], lang: str = "en") -> str:
    """Text table of the demo results.

    Every column is as wide as its widest cell, measured in display columns (Hangul takes two),
    so the table lines up in Korean as well as in English.
    """
    heads = [t(k, lang=lang) for k in
             ("col_case", "col_base_sps", "col_route", "col_final_sps", "col_target", "col_err", "col_warnings")]
    body = [
        [name, f"{r.base.measurement.sps:.2f}", t(f"kind_{r.route}", lang=lang), f"{r.best.measurement.sps:.2f}",
         f"{r.target_sps:.1f}", f"{r.best.err_pct:.2f}%", ", ".join(r.warnings) or "-"]
        for name, r in results
    ]
    minimum = [9, 8, 14, 9, 6, 7, 0]  # the English layout of earlier versions
    widths = [max([minimum[i], display_width(heads[i])] + [display_width(row[i]) for row in body])
              for i in range(7)]
    align = ["<", ">", "<", ">", ">", ">", "<"]
    gaps = [" ", "  ", " ", " ", " ", "  "]  # text between neighbouring columns

    def line(cells: list[str]) -> str:
        out = pad(cells[0], widths[0], align[0])
        for i in range(1, 7):
            out += gaps[i - 1] + (cells[i] if i == 6 else pad(cells[i], widths[i], align[i]))
        return out

    head = line(heads)
    return "\n".join([head, "-" * display_width(head), *(line(row) for row in body)])
