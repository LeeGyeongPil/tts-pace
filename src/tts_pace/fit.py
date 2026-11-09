"""Closed-loop fitting: measure, re-synthesize once with the engine knob, finish with a bounded tempo."""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path

from .audio import AudioClip
from .cache import ResultCache, audio_hash, default_cache_dir, make_key
from .count import SyllableCount, count_syllables
from .engines.base import SpeedEngine
from .measure import Measurement, measure
from .runtime import DEFAULT_LIMITER, Limiter, run_dir
from .tempo import DEFAULT_TEMPO_RANGE, clamp_factor, resolve_backend, retime

# The knob counts as "weak" when the rate moved less than this share of the change we asked for.
WEAK_RESPONSE = 0.5
# Tempo changes smaller than this are not worth an audio pass.
MIN_TEMPO_DELTA = 0.002

ADVICE = {
    "knob_response_weak": "The engine speed knob changed the pace much less than asked (it may stop at a floor "
                          "or scale non-linearly). Try another voice or engine setting, or edit the text.",
    "knob_clamped": "The requested engine speed was outside the engine's range and was cut to it.",
    "tempo_clamped": "The tempo change hit its limit, so the target was not reached. Shorten or lengthen the "
                     "text, or choose an engine setting closer to the target pace.",
    "unsupported_chars": "Some characters were not counted (for example kanji); give a spoken form with "
                         "normalize={...} for accurate rates.",
}


@dataclass(frozen=True)
class Candidate:
    """One audio version tried by fit().

    kind: 'base' | 'tempo-only' | 'resynth' | 'resynth+tempo'. speed is the engine speed used
    (1.0 = default); tempo is the pitch-preserving tempo factor applied afterwards (1.0 = none).
    """

    kind: str
    path: str | None
    speed: float
    tempo: float
    measurement: Measurement
    err_pct: float

    def to_dict(self) -> dict[str, object]:
        return {"kind": self.kind, "path": self.path, "speed": round(self.speed, 4),
                "tempo": round(self.tempo, 4), "measurement": self.measurement.to_dict(),
                "err_pct": round(self.err_pct, 3)}

    @classmethod
    def from_dict(cls, d: Mapping[str, object]) -> Candidate:
        return cls(str(d["kind"]), d["path"] and str(d["path"]) or None, float(d["speed"]),  # type: ignore[arg-type]
                   float(d["tempo"]), Measurement.from_dict(d["measurement"]), float(d["err_pct"]))  # type: ignore[arg-type]


@dataclass(frozen=True)
class FitResult:
    """Outcome of fit(): ``best`` is the candidate closest to the target, ``base`` the first synthesis."""

    target_sps: float
    engine: str
    mock: bool
    syllables: SyllableCount
    base: Candidate
    candidates: tuple[Candidate, ...]
    best: Candidate
    first_ratio: float
    warnings: tuple[str, ...]
    advice: tuple[str, ...]
    cache_hit: bool = False
    cache_key: str | None = None

    @property
    def route(self) -> str:
        """How the best candidate was made: base, tempo-only, resynth or resynth+tempo."""
        return self.best.kind

    def report(self) -> dict[str, object]:
        return {
            "version": 1,
            "engine": self.engine,
            "mock": self.mock,
            "mock_note": "practice (mock) engine, not a real TTS" if self.mock else None,
            "target_sps": self.target_sps,
            "syllables": self.syllables.to_dict(),
            "first_ratio": round(self.first_ratio, 4),
            "route": self.route,
            "best": self.candidates.index(self.best),
            "candidates": [c.to_dict() for c in self.candidates],
            "warnings": list(self.warnings),
            "advice": list(self.advice),
            "cache_hit": self.cache_hit,
            "cache_key": self.cache_key,
        }

    @classmethod
    def from_report(cls, r: Mapping[str, object], *, cache_hit: bool = False, best_path: str | None = None) -> FitResult:
        cands = tuple(Candidate.from_dict(c) for c in r["candidates"])  # type: ignore[attr-defined]
        best = cands[int(r["best"])]  # type: ignore[call-overload]
        if best_path:
            cands = tuple(replace(c, path=best_path) if c is best else c for c in cands)
            best = cands[int(r["best"])]  # type: ignore[call-overload]
        s = r["syllables"]
        syl = SyllableCount(int(s["total"]), dict(s["by_script"]), str(s["normalized_text"]), tuple(s["unsupported"]))  # type: ignore[index]
        return cls(float(r["target_sps"]), str(r["engine"]), bool(r["mock"]), syl, cands[0], cands, best,  # type: ignore[arg-type]
                   float(r["first_ratio"]), tuple(r["warnings"]), tuple(r["advice"]),  # type: ignore[arg-type]
                   cache_hit, r.get("cache_key"))  # type: ignore[arg-type]

    def save_report(self, path: str | Path) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.report(), ensure_ascii=False, indent=2), encoding="utf-8")
        return p


def _err(sps: float, target: float) -> float:
    return abs(sps - target) / target * 100.0


def _validate(target_sps: float, tolerance: float, tempo_range: tuple[float, float]) -> None:
    if not target_sps > 0:
        raise ValueError(f"target_sps must be positive (syllables per second, e.g. 5.0), got {target_sps!r}")
    if not 0 <= tolerance < 1:
        raise ValueError(f"tolerance must be in [0, 1), e.g. 0.10 for 10%, got {tolerance!r}")
    lo, hi = tempo_range
    if not (0 < lo <= 1 <= hi):
        raise ValueError(f"tempo_range must satisfy 0 < low <= 1 <= high, got {tempo_range!r}")


def _loop(
    *,
    count: SyllableCount,
    target: float,
    base_clip: AudioClip,
    resynth: Callable[[float], AudioClip] | None,
    speed_range: tuple[float, float],
    engine_name: str,
    mock: bool,
    tolerance: float,
    tempo_range: tuple[float, float],
    silence_db: float,
    min_silence: float,
    tempo_backend: str,
    measure_backend: str,
    limiter: Limiter,
) -> tuple[FitResult, dict[str, AudioClip]]:
    """The 2-step loop. Returns the result and the audio of every candidate by kind."""

    def meas(clip: AudioClip) -> Measurement:
        return measure(clip, syllables=count.total, silence_db=silence_db, min_silence=min_silence,
                       backend=measure_backend, limiter=limiter)

    warns: list[str] = []
    if count.unsupported:
        warns.append("unsupported_chars")
    cands: list[Candidate] = []
    clips: dict[str, AudioClip] = {}

    m0 = meas(base_clip)
    assert m0.sps is not None
    base = Candidate("base", None, 1.0, 1.0, m0, _err(m0.sps, target))
    cands.append(base)
    clips["base"] = base_clip
    ratio = target / m0.sps
    first_ratio = ratio

    cur_clip, cur_m, speed = base_clip, m0, 1.0
    if resynth is not None and abs(ratio - 1.0) > tolerance:
        want = speed * ratio
        lo, hi = speed_range
        speed = min(max(want, lo), hi)
        if speed != want:
            warns.append("knob_clamped")
        cur_clip = resynth(speed)
        cur_m = meas(cur_clip)
        assert cur_m.sps is not None
        cands.append(Candidate("resynth", None, speed, 1.0, cur_m, _err(cur_m.sps, target)))
        clips["resynth"] = cur_clip
        asked, got = ratio - 1.0, cur_m.sps / m0.sps - 1.0
        if abs(got) < WEAK_RESPONSE * abs(asked):
            warns.append("knob_response_weak")
        kind_with_tempo = "resynth+tempo"
    else:
        kind_with_tempo = "tempo-only"

    assert cur_m.sps is not None
    remaining = target / cur_m.sps
    if abs(remaining - 1.0) > MIN_TEMPO_DELTA:
        factor, clamped = clamp_factor(remaining, tempo_range)
        if clamped:
            warns.append("tempo_clamped")
        out_clip = retime(cur_clip, factor, backend=tempo_backend, clamp=True, tempo_range=tempo_range,
                          limiter=limiter)
        m2 = meas(out_clip)
        assert m2.sps is not None
        cands.append(Candidate(kind_with_tempo, None, speed, factor, m2, _err(m2.sps, target)))
        clips[kind_with_tempo] = out_clip

    best = min(cands, key=lambda c: c.err_pct)
    warns = list(dict.fromkeys(warns))
    advice = tuple(ADVICE[w] for w in warns)
    result = FitResult(target, engine_name, mock, count, base, tuple(cands), best, first_ratio,
                       tuple(warns), advice)
    return result, clips


def _finish(result: FitResult, clips: dict[str, AudioClip], out: str | Path | None,
            keep_candidates: bool) -> FitResult:
    """Write WAV files and fill in candidate paths."""
    if out is None:
        return result
    out_path = Path(out)
    paths: dict[str, str] = {}
    clips[result.best.kind].to_wav(out_path)
    paths[result.best.kind] = str(out_path)
    if keep_candidates:
        for kind, clip in clips.items():
            if kind not in paths:
                slug = kind.replace("+", "-")  # 'resynth+tempo' -> 'resynth-tempo'
                p = out_path.with_name(f"{out_path.stem}_{slug}.wav")
                clip.to_wav(p)
                paths[kind] = str(p)
    cands = tuple(replace(c, path=paths.get(c.kind)) for c in result.candidates)
    best = cands[result.candidates.index(result.best)]
    return replace(result, base=cands[0], candidates=cands, best=best)


def fit(
    text: str,
    target_sps: float,
    engine: SpeedEngine,
    out: str | Path | None = None,
    *,
    tolerance: float = 0.10,
    tempo_range: tuple[float, float] = DEFAULT_TEMPO_RANGE,
    silence_db: float = -60.0,
    min_silence: float = 0.6,
    cache_dir: str | Path | bool | None = None,
    tempo_backend: str = "auto",
    measure_backend: str = "auto",
    limiter: Limiter | None = None,
    lang: str = "auto",
    normalize: Mapping[str, str] | None = None,
    keep_candidates: bool = False,
) -> FitResult:
    """Make ``engine`` speak ``text`` at ``target_sps`` syllables per second of pure speech.

    Steps: synthesize at the default speed, measure, then either only apply a tempo change
    (when within ``tolerance`` of the target, or the engine has no speed knob) or re-synthesize
    once with speed x ratio and finish with a tempo change limited to ``tempo_range``.

    ``cache_dir``: a folder to reuse results (None = use TTS_PACE_CACHE_DIR if set, else no
    cache; False = never cache). ``out``: where to write the best WAV.
    Raises ValueError for bad arguments, UnsupportedTextError, MeasurementError, EngineError, BusyError.
    """
    _validate(target_sps, tolerance, tempo_range)
    lim = limiter or DEFAULT_LIMITER
    count = count_syllables(text, lang, normalize)
    info = engine.info
    tempo_used = resolve_backend(tempo_backend)

    cache: ResultCache | None = None
    if cache_dir is not False:
        if cache_dir is True:
            cache = ResultCache(default_cache_dir())
        elif cache_dir is not None:
            cache = ResultCache(cache_dir)
        elif os.environ.get("TTS_PACE_CACHE_DIR"):
            cache = ResultCache(default_cache_dir())

    def key_for(base_id: str) -> str:
        return make_key({
            "engine": info.cache_id, "text": text, "lang": lang, "normalize": dict(normalize or {}),
            "target": target_sps, "tolerance": tolerance, "tempo_range": list(tempo_range),
            "silence_db": silence_db, "min_silence": min_silence, "tempo": tempo_used,
            "measure": "ffmpeg" if measure_backend == "ffmpeg" else "numpy",
            "speed_range": list(info.speed_range), "knob": info.has_speed_knob, "base": base_id,
        })

    def from_cache(key: str) -> FitResult | None:
        assert cache is not None
        hit = cache.get(key)
        if hit is None:
            return None
        report, wav = hit
        dest = str(cache.copy_wav(key, out)) if out is not None else str(wav)
        return FitResult.from_report(report, cache_hit=True, best_path=dest)

    key: str | None = None
    if cache is not None and info.deterministic:
        # Deterministic engine: the base audio is fully described by (cache_id, text, speed 1.0).
        key = key_for(f"det:{info.cache_id}:1.0")
        cached = from_cache(key)
        if cached is not None:
            return cached

    with run_dir():  # one temp folder per run; removed even when the engine raises
        lo, hi = info.speed_range
        base_speed = min(max(1.0, lo), hi)
        with lim.slot():
            base_clip = engine.synthesize(text, base_speed)
        if cache is not None and not info.deterministic:
            # Non-deterministic engine: the key has to include what the engine actually produced.
            key = key_for(f"audio:{audio_hash(base_clip)}")
            cached = from_cache(key)
            if cached is not None:
                return cached

        def resynth(speed: float) -> AudioClip:
            with lim.slot():
                return engine.synthesize(text, speed)

        result, clips = _loop(
            count=count, target=target_sps, base_clip=base_clip,
            resynth=resynth if info.has_speed_knob else None, speed_range=info.speed_range,
            engine_name=info.name, mock=info.is_mock, tolerance=tolerance, tempo_range=tempo_range,
            silence_db=silence_db, min_silence=min_silence, tempo_backend=tempo_backend,
            measure_backend=measure_backend, limiter=lim,
        )
    result = replace(result, cache_key=key)
    if cache is not None and key is not None:
        cache.put(key, result.report(), clips[result.best.kind])
    return _finish(result, clips, out, keep_candidates)


def fit_audio(
    audio: str | Path | AudioClip,
    text: str,
    target_sps: float,
    out: str | Path | None = None,
    *,
    tolerance: float = 0.10,
    tempo_range: tuple[float, float] = DEFAULT_TEMPO_RANGE,
    silence_db: float = -60.0,
    min_silence: float = 0.6,
    tempo_backend: str = "auto",
    measure_backend: str = "auto",
    limiter: Limiter | None = None,
    lang: str = "auto",
    normalize: Mapping[str, str] | None = None,
) -> FitResult:
    """Fit an existing recording with the tempo change only (no engine). Same result type as fit()."""
    _validate(target_sps, tolerance, tempo_range)
    count = count_syllables(text, lang, normalize)
    clip = audio if isinstance(audio, AudioClip) else AudioClip.from_wav(audio)
    result, clips = _loop(
        count=count, target=target_sps, base_clip=clip, resynth=None, speed_range=(1.0, 1.0),
        engine_name="file", mock=False, tolerance=tolerance, tempo_range=tempo_range,
        silence_db=silence_db, min_silence=min_silence, tempo_backend=tempo_backend,
        measure_backend=measure_backend, limiter=limiter or DEFAULT_LIMITER,
    )
    return _finish(result, clips, out, False)
