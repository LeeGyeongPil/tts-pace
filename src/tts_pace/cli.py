"""Command line interface: demo, count, measure, retime, fit.

Screen language: ``--lang en|ko`` before the command, else TTS_PACE_LANG, else LC_ALL/LC_MESSAGES/LANG
(see ``tts_pace.i18n``). The ``--lang`` after ``count``/``fit`` is a different option (text language /
mock engine preset) and keeps its old meaning.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
import warnings
from collections.abc import Iterator
from pathlib import Path

from . import __version__
from .cache import default_cache_dir
from .count import UnsupportedCharsWarning, count_syllables
from .demo import banner, format_table, run_demo
from .engines import MockEngine, PiperEngine, SayEngine
from .errors import CodedValueError, TtsPaceError
from .fit import FitResult, fit, fit_audio
from .i18n import LANGS, MESSAGES, argparse_gettext, pad, render_error, resolve_lang, t
from .measure import measure


def _lang_of(args: argparse.Namespace) -> str:
    """Screen language chosen for this run (set by main(); English when a handler is called directly)."""
    return getattr(args, "screen_lang", "en")


def _pre_scan_lang(argv: list[str]) -> str | None:
    """Find a top-level ``--lang en|ko`` that comes before the first command word.

    Only the arguments before the command are looked at, so ``count --lang ko`` (text language)
    and ``fit --lang en`` (mock engine preset) are never mistaken for the screen language.
    """
    pre = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    pre.add_argument("--lang", default=None)
    head: list[str] = []
    skip_value = False
    for token in argv:
        if skip_value:
            head.append(token)
            skip_value = False
        elif token == "--lang":
            head.append(token)
            skip_value = True
        elif token.startswith("-"):
            head.append(token)
        else:
            break  # the command word: everything after it belongs to the command
    known, _ = pre.parse_known_args(head)
    return known.lang if known.lang in LANGS else None


@contextlib.contextmanager
def _argparse_lang(lang: str) -> Iterator[None]:
    """Make argparse's own fixed phrases (usage:, error:, ...) come out in ``lang`` inside the block."""
    original = argparse._  # type: ignore[attr-defined]
    argparse._ = argparse_gettext(lang)  # type: ignore[attr-defined]
    try:
        yield
    finally:
        argparse._ = original  # type: ignore[attr-defined]


def _text_arg(args: argparse.Namespace) -> str:
    if getattr(args, "text", None) is not None:
        return args.text
    if getattr(args, "text_file", None):
        try:
            return Path(args.text_file).read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise CodedValueError(f"--text-file {args.text_file} is not valid UTF-8 text. "
                                  "Re-save the file as UTF-8 and try again.",
                                  code="text_file_not_utf8", params={"path": args.text_file}) from exc
        except OSError as exc:
            raise CodedValueError(f"Cannot read --text-file {args.text_file}: {exc}",
                                  code="text_file_unreadable",
                                  params={"path": args.text_file, "reason": str(exc)}) from exc
    raise CodedValueError("Give the script with --text TEXT or --text-file FILE.", code="text_missing")


def _add_text(p: argparse.ArgumentParser, lang: str, required: bool = True) -> None:
    g = p.add_mutually_exclusive_group(required=required)
    g.add_argument("--text", help=t("help_text", lang=lang))
    g.add_argument("--text-file", help=t("help_text_file", lang=lang))


def _add_target(p: argparse.ArgumentParser, lang: str) -> None:
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--target", type=float, help=t("help_target", lang=lang))
    g.add_argument("--target-duration", type=float, metavar="SECONDS", help=t("help_target_duration", lang=lang))


def _row(lang: str, label_key: str, value: str) -> str:
    """One 'label   value' line; the label column is padded by display width (Korean = 2 columns/char)."""
    return f"{pad(t(label_key, lang=lang), 9)} {value}"


def _print_warnings(r: FitResult, lang: str) -> None:
    """Warning lines on stderr. The code stays as is; the advice text is shown in the screen language."""
    for w, a in zip(r.warnings, r.advice):
        key = f"advice_{w}"
        advice = t(key, lang=lang) if key in MESSAGES["en"] else a
        print(f"{t('warning_prefix', lang=lang)}: {w} - {advice}", file=sys.stderr)


def _print_result(r: FitResult, out: str | None, lang: str = "en") -> None:
    print(_row(lang, "label_base", t("base_value", lang=lang, sps=r.base.measurement.sps)))
    for c in r.candidates[1:]:
        detail = t("candidate", lang=lang, speed=c.speed, tempo=c.tempo, sps=c.measurement.sps, err=c.err_pct)
        print(f"{pad(t(f'kind_{c.kind}', lang=lang), 13)} {detail}")
    route = t(f"kind_{r.route}", lang=lang)
    print(_row(lang, "label_best", t("best_value", lang=lang, route=route, sps=r.best.measurement.sps,
                                     target=r.target_sps, err=r.best.err_pct)))
    if r.target_duration is not None:  # length mode only
        print(_row(lang, "label_length", t("length_value", lang=lang, total=r.best.measurement.total_s,
                                           target=r.target_duration, err=r.length_err_pct)))
    print(_row(lang, "label_cache", t("cache_hit" if r.cache_hit else "cache_miss", lang=lang)))
    if out:
        print(_row(lang, "label_wrote", out))
    _print_warnings(r, lang)


def cmd_demo(args: argparse.Namespace) -> int:
    lang = _lang_of(args)
    print(banner(lang))
    results, report_path = run_demo(args.out)
    print(format_table(results, lang))
    print("\n" + t("demo_wrote", lang=lang, out=args.out, report=report_path))
    return 0


def cmd_count(args: argparse.Namespace) -> int:
    lang = _lang_of(args)
    c = count_syllables(args.text, args.lang)  # args.lang here is the text language, not the screen language
    if args.json:
        print(json.dumps(c.to_dict(), ensure_ascii=False))
    else:
        def line(key: str, value: str) -> str:
            return f"{pad(t(key, lang=lang), 11)} : {value}"

        print(line("label_spoken", c.normalized_text))
        print(line("label_syllables", f"{c.total}  {c.by_script}"))
        if c.unsupported:
            print(line("label_unsupported", " ".join(c.unsupported)))
    return 0


def cmd_measure(args: argparse.Namespace) -> int:
    lang = _lang_of(args)
    text = _text_arg(args) if (args.text is not None or args.text_file) else None
    m = measure(args.wav, text, silence_db=args.silence_db, min_silence=args.min_silence, backend=args.backend)
    if args.json:
        print(json.dumps(m.to_dict()))
    else:
        print(t("measure_line1", lang=lang, total=m.total_s, silence=m.silence_s, gaps=m.gaps, net=m.net_s))
        if m.sps is not None:
            print(t("measure_line2", lang=lang, syllables=m.syllables, sps=m.sps))
    return 0


def cmd_retime(args: argparse.Namespace) -> int:
    lang = _lang_of(args)
    r = fit_audio(args.wav, _text_arg(args), args.target, out=args.out, target_duration=args.target_duration)
    if args.json:
        print(json.dumps(r.report(), ensure_ascii=False))
    else:
        _print_result(r, args.out, lang)
        return 0
    _print_warnings(r, lang)
    return 0  # reaching the tempo limit is a warning, not a failure


def cmd_fit(args: argparse.Namespace) -> int:
    lang = _lang_of(args)
    text = _text_arg(args)
    if args.engine == "mock":
        preset = args.lang or ("ko" if any("가" <= ch <= "힣" for ch in text) else "en")
        engine = MockEngine(preset)
        # With --json stdout must hold the JSON only, so the practice-mode notice goes to stderr.
        print(banner(lang), file=sys.stderr if args.json else sys.stdout)
    elif args.engine == "say":
        engine = SayEngine(args.voice)
    else:
        engine = PiperEngine(args.voice)
    cache_dir = args.cache_dir if args.cache_dir else (False if args.no_cache else default_cache_dir())
    r = fit(text, args.target, engine, out=args.out, cache_dir=cache_dir, target_duration=args.target_duration)
    if args.json:
        print(json.dumps(r.report(), ensure_ascii=False))
        _print_warnings(r, lang)
        if args.report:
            r.save_report(args.report)
        return 0
    _print_result(r, args.out, lang)
    if args.report:
        r.save_report(args.report)
        print(_row(lang, "label_report", args.report))
    return 0


def build_parser(lang: str | None = None) -> argparse.ArgumentParser:
    """Build the parser with help texts in ``lang`` (default: resolved from the environment)."""
    lang = lang if lang in LANGS else resolve_lang()
    with _argparse_lang(lang):
        return _build_parser(lang)


def _build_parser(lang: str) -> argparse.ArgumentParser:
    def h(key: str) -> str:
        return t(key, lang=lang)

    p = argparse.ArgumentParser(prog="tts-pace", description=h("description"))
    p.add_argument("--version", action="version", version=f"tts-pace {__version__}")
    # Screen language. dest differs from the subcommands' own --lang so the two never overwrite each other.
    p.add_argument("--lang", dest="ui_lang", choices=list(LANGS), default=None, help=h("help_lang"))
    sub = p.add_subparsers(dest="command", required=True)

    d = sub.add_parser("demo", help=h("help_demo"))
    d.add_argument("--out", default="tts-pace-demo", help=h("help_demo_out"))
    d.set_defaults(func=cmd_demo)

    c = sub.add_parser("count", help=h("help_count"))
    c.add_argument("text")
    c.add_argument("--lang", choices=["auto", "ko", "en", "ja"], default="auto", help=h("help_count_lang"))
    c.add_argument("--json", action="store_true", help=h("help_json_count"))
    c.set_defaults(func=cmd_count)

    m = sub.add_parser("measure", help=h("help_measure"))
    m.add_argument("wav")
    _add_text(m, lang, required=False)
    m.add_argument("--silence-db", type=float, default=-60.0)
    m.add_argument("--min-silence", type=float, default=0.6)
    m.add_argument("--backend", choices=["auto", "numpy", "ffmpeg"], default="auto")
    m.add_argument("--json", action="store_true", help=h("help_json_measure"))
    m.set_defaults(func=cmd_measure)

    r = sub.add_parser("retime", help=h("help_retime"))
    r.add_argument("wav")
    _add_text(r, lang)
    _add_target(r, lang)
    r.add_argument("-o", "--out", required=True)
    r.add_argument("--json", action="store_true", help=h("help_json_retime"))
    r.set_defaults(func=cmd_retime)

    f = sub.add_parser("fit", help=h("help_fit"))
    f.add_argument("--engine", choices=["mock", "say", "piper"], default="mock")
    _add_text(f, lang)
    _add_target(f, lang)
    f.add_argument("-o", "--out", required=True)
    f.add_argument("--voice", help=h("help_voice"))
    f.add_argument("--lang", choices=["ko", "en"], help=h("help_fit_lang"))
    f.add_argument("--cache-dir", help=t("help_cache_dir", lang=lang, path=default_cache_dir()))
    f.add_argument("--no-cache", action="store_true", help=h("help_no_cache"))
    f.add_argument("--report", help=h("help_report"))
    f.add_argument("--json", action="store_true", help=h("help_json_fit"))
    f.set_defaults(func=cmd_fit)
    return p


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    lang = resolve_lang(_pre_scan_lang(argv))
    with _argparse_lang(lang):
        args = build_parser(lang).parse_args(argv)
    args.screen_lang = lang
    prefix = t("error_prefix", lang=lang)
    try:
        with warnings.catch_warnings():
            # The CLI prints its own localized "unsupported" line and warning code, so hide the Python warning.
            warnings.simplefilter("ignore", UnsupportedCharsWarning)
            return int(args.func(args))
    except (TtsPaceError, ValueError) as exc:
        print(f"{prefix}: {render_error(exc, lang)}", file=sys.stderr)
        return 2
    except OSError as exc:
        # File-system problems (unwritable output path, missing folder, ...) get a short hint, not a traceback.
        target = exc.filename if exc.filename is not None else t("output_path_default", lang=lang)
        reason = exc.strerror or str(exc)
        print(f"{prefix}: {t('cannot_write', lang=lang, target=target, reason=reason)}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
