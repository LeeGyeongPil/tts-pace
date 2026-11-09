import pytest

from tts_pace import CallableEngine, MockEngine, fit
from tts_pace.cache import ResultCache

EN = "Today we learn how to match the speaking rate of a synthetic voice. It is a short lesson."
KW = {"tempo_backend": "numpy", "measure_backend": "numpy"}


def test_second_fit_is_a_hit_without_engine_calls(tmp_path):
    engine = MockEngine("en")
    first = fit(EN, 4.0, engine, cache_dir=tmp_path, out=tmp_path / "a.wav", **KW)
    calls = len(engine.calls)
    second = fit(EN, 4.0, engine, cache_dir=tmp_path, out=tmp_path / "b.wav", **KW)
    assert not first.cache_hit and second.cache_hit
    assert len(engine.calls) == calls  # no extra synthesis
    assert second.best.err_pct == pytest.approx(first.best.err_pct, abs=1e-3)
    assert (tmp_path / "b.wav").read_bytes() == (tmp_path / "a.wav").read_bytes()


def test_changing_the_target_misses(tmp_path):
    engine = MockEngine("en")
    a = fit(EN, 4.0, engine, cache_dir=tmp_path, **KW)
    b = fit(EN, 4.1, engine, cache_dir=tmp_path, **KW)
    assert not b.cache_hit and a.cache_key != b.cache_key


def test_non_deterministic_engine_key_includes_audio_hash(tmp_path):
    a = fit(EN, 4.0, MockEngine("en", jitter=0.08), cache_dir=tmp_path, **KW)
    b = fit(EN, 4.0, MockEngine("en", jitter=0.08), cache_dir=tmp_path, **KW)
    assert a.cache_key != b.cache_key and not b.cache_hit  # different base audio -> different key


def test_non_deterministic_engine_hits_when_audio_is_identical(tmp_path):
    fixed = MockEngine("en").synthesize(EN, 1.0)
    engine = CallableEngine(lambda t, s: fixed, name="fixed")  # not declared deterministic
    a = fit(EN, 4.8, engine, cache_dir=tmp_path, **KW)
    b = fit(EN, 4.8, engine, cache_dir=tmp_path, **KW)
    assert b.cache_hit and a.cache_key == b.cache_key


def test_cache_is_off_without_directory(tmp_path, monkeypatch):
    monkeypatch.delenv("TTS_PACE_CACHE_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    fit(EN, 4.0, MockEngine("en"), **KW)
    assert not list(tmp_path.iterdir())  # nothing is written unless asked


def test_cache_directory_from_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("TTS_PACE_CACHE_DIR", str(tmp_path / "c"))
    fit(EN, 4.0, MockEngine("en"), **KW)
    assert fit(EN, 4.0, MockEngine("en"), **KW).cache_hit


def test_cache_has_an_upper_bound(tmp_path):
    engine = MockEngine("en")
    cache = ResultCache(tmp_path, max_entries=2)
    for target in (4.0, 4.1, 4.2):
        r = fit(EN, target, engine, cache_dir=False, **KW)
        key = f"k{target}"
        import os
        import time

        cache.put(key, r.report(), engine.synthesize(EN, 1.0))
        os.utime(tmp_path / f"{key}.json", (time.time(), time.time()))
        time.sleep(0.02)
    assert len(list(tmp_path.glob("*.json"))) == 2
    assert cache.get("k4.0") is None


def test_damaged_entry_counts_as_miss(tmp_path):
    engine = MockEngine("en")
    a = fit(EN, 4.0, engine, cache_dir=tmp_path, **KW)
    (tmp_path / f"{a.cache_key}.json").write_text("{not json")
    assert not fit(EN, 4.0, engine, cache_dir=tmp_path, **KW).cache_hit
