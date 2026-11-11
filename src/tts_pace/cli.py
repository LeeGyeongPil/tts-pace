"""Command line interface: demo, count, measure, retime, fit."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .cache import default_cache_dir
from .count import count_syllables
from .demo import MOCK_BANNER, format_table, run_demo
from .engines import MockEngine, PiperEngine, SayEngine
from .errors import TtsPaceError
from .fit import FitResult, fit, fit_audio
from .measure import measure


def _text_arg(args: argparse.Namespace) -> str:
    if getattr(args, "text", None) is not None:
        return args.text
    if getattr(args, "text_file", None):
        try:
            return Path(args.text_file).read_text(encoding="utf-8")
        except OSError as exc:
            raise ValueError(f"Cannot read --text-file {args.text_file}: {exc}") from exc
    raise ValueError("Give the script with --text TEXT or --text-file FILE.")


def _add_text(p: argparse.ArgumentParser, required: bool = True) -> None:
    g = p.add_mutually_exclusive_group(required=required)
    g.add_argument("--text", help="the spoken text")
    g.add_argument("--text-file", help="file containing the spoken text (UTF-8)")


def _add_target(p: argparse.ArgumentParser) -> None:
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--target", type=float, help="target syllables per second")
    g.add_argument("--target-duration", type=float, metavar="SECONDS",
                   help="target total length in seconds, pauses included")


def _print_result(r: FitResult, out: str | None) -> None:
    print(f"base      {r.base.measurement.sps:.2f} sps")
    for c in r.candidates[1:]:
        print(f"{c.kind:<13} speed x{c.speed:.3f}  tempo x{c.tempo:.3f}  -> {c.measurement.sps:.2f} sps  err {c.err_pct:.2f}%")
    print(f"best      {r.route}: {r.best.measurement.sps:.2f} sps (target {r.target_sps:g}, err {r.best.err_pct:.2f}%)")
    if r.target_duration is not None:  # length mode only
        print(f"length    {r.best.measurement.total_s:.2f}s (target {r.target_duration:.2f}s, err {r.length_err_pct:.2f}%)")
    print(f"cache     {'hit' if r.cache_hit else 'miss'}")
    if out:
        print(f"wrote     {out}")
    for w, a in zip(r.warnings, r.advice):
        print(f"warning: {w} - {a}", file=sys.stderr)


def cmd_demo(args: argparse.Namespace) -> int:
    print(MOCK_BANNER)
    results, report_path = run_demo(args.out)
    print(format_table(results))
    print(f"\nwrote {args.out}/ (WAV files + report.json: {report_path})")
    return 0


def cmd_count(args: argparse.Namespace) -> int:
    c = count_syllables(args.text, args.lang)
    if args.json:
        print(json.dumps(c.to_dict(), ensure_ascii=False))
    else:
        print(f"spoken form : {c.normalized_text}")
        print(f"syllables   : {c.total}  {c.by_script}")
        if c.unsupported:
            print(f"unsupported : {' '.join(c.unsupported)}")
    return 0


def cmd_measure(args: argparse.Namespace) -> int:
    text = _text_arg(args) if (args.text is not None or args.text_file) else None
    m = measure(args.wav, text, silence_db=args.silence_db, min_silence=args.min_silence, backend=args.backend)
    if args.json:
        print(json.dumps(m.to_dict()))
    else:
        print(f"total {m.total_s:.2f}s  silence {m.silence_s:.2f}s ({m.gaps} gaps)  speech {m.net_s:.2f}s")
        if m.sps is not None:
            print(f"{m.syllables} syllables -> {m.sps:.2f} syllables/second of pure speech")
    return 0


def cmd_retime(args: argparse.Namespace) -> int:
    r = fit_audio(args.wav, _text_arg(args), args.target, out=args.out, target_duration=args.target_duration)
    if args.json:
        print(json.dumps(r.report(), ensure_ascii=False))
    else:
        _print_result(r, args.out)
        return 0
    for w, a in zip(r.warnings, r.advice):
        print(f"warning: {w} - {a}", file=sys.stderr)
    return 0  # reaching the tempo limit is a warning, not a failure


def cmd_fit(args: argparse.Namespace) -> int:
    text = _text_arg(args)
    if args.engine == "mock":
        preset = args.lang or ("ko" if any("가" <= ch <= "힣" for ch in text) else "en")
        engine = MockEngine(preset)
        # With --json stdout must hold the JSON only, so the practice-mode notice goes to stderr.
        print(MOCK_BANNER, file=sys.stderr if args.json else sys.stdout)
    elif args.engine == "say":
        engine = SayEngine(args.voice)
    else:
        engine = PiperEngine(args.voice)
    cache_dir = args.cache_dir if args.cache_dir else (False if args.no_cache else default_cache_dir())
    r = fit(text, args.target, engine, out=args.out, cache_dir=cache_dir, target_duration=args.target_duration)
    if args.json:
        print(json.dumps(r.report(), ensure_ascii=False))
        for w, a in zip(r.warnings, r.advice):
            print(f"warning: {w} - {a}", file=sys.stderr)
        if args.report:
            r.save_report(args.report)
        return 0
    _print_result(r, args.out)
    if args.report:
        r.save_report(args.report)
        print(f"report    {args.report}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="tts-pace", description="Measure and fit TTS speaking rate (syllables/second).")
    p.add_argument("--version", action="version", version=f"tts-pace {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    d = sub.add_parser("demo", help="run four fits with the practice (mock) engine")
    d.add_argument("--out", default="tts-pace-demo", help="output folder (default: ./tts-pace-demo)")
    d.set_defaults(func=cmd_demo)

    c = sub.add_parser("count", help="show the spoken form and syllable count of a text")
    c.add_argument("text")
    c.add_argument("--lang", choices=["auto", "ko", "en", "ja"], default="auto")
    c.add_argument("--json", action="store_true")
    c.set_defaults(func=cmd_count)

    m = sub.add_parser("measure", help="measure a WAV file")
    m.add_argument("wav")
    _add_text(m, required=False)
    m.add_argument("--silence-db", type=float, default=-60.0)
    m.add_argument("--min-silence", type=float, default=0.6)
    m.add_argument("--backend", choices=["auto", "numpy", "ffmpeg"], default="auto")
    m.add_argument("--json", action="store_true")
    m.set_defaults(func=cmd_measure)

    r = sub.add_parser("retime", help="change an existing recording's tempo toward a target rate (0.85-1.15 limit)")
    r.add_argument("wav")
    _add_text(r)
    _add_target(r)
    r.add_argument("-o", "--out", required=True)
    r.add_argument("--json", action="store_true")
    r.set_defaults(func=cmd_retime)

    f = sub.add_parser("fit", help="synthesize with an engine and fit to a target rate")
    f.add_argument("--engine", choices=["mock", "say", "piper"], default="mock")
    _add_text(f)
    _add_target(f)
    f.add_argument("-o", "--out", required=True)
    f.add_argument("--voice", help="say voice name, or Piper .onnx path")
    f.add_argument("--lang", choices=["ko", "en"], help="mock engine preset (default: guessed from the text)")
    f.add_argument("--cache-dir", help=f"result cache folder (default: {default_cache_dir()})")
    f.add_argument("--no-cache", action="store_true")
    f.add_argument("--report", help="write the report JSON here")
    f.add_argument("--json", action="store_true", help="print the report JSON to stdout (notices go to stderr)")
    f.set_defaults(func=cmd_fit)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except (TtsPaceError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        # File-system problems (unwritable output path, missing folder, ...) get a short hint, not a traceback.
        target = exc.filename if exc.filename is not None else "the output path"
        print(
            f"error: cannot write {target}: {exc.strerror or exc}. Choose a writable folder with -o.",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
