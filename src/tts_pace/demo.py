"""`tts-pace demo`: four fits with the practice (mock) engine, no keys or real TTS needed."""

from __future__ import annotations

import json
from pathlib import Path

from .engines.mock import MockEngine
from .fit import FitResult, fit

MOCK_BANNER = "[mock] 연습용 목(mock) 엔진 — 실제 TTS 아님 (practice engine, not a real TTS)"

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


def format_table(results: list[tuple[str, FitResult]]) -> str:
    head = f"{'case':<9} {'base sps':>8}  {'route':<14} {'final sps':>9} {'target':>6} {'err':>7}  warnings"
    lines = [head, "-" * len(head)]
    for name, r in results:
        lines.append(
            f"{name:<9} {r.base.measurement.sps:>8.2f}  {r.route:<14} {r.best.measurement.sps:>9.2f} "
            f"{r.target_sps:>6.1f} {r.best.err_pct:>6.2f}%  {', '.join(r.warnings) or '-'}"
        )
    return "\n".join(lines)
