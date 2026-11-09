"""Smallest example: fit one sentence to 4.0 syllables/second with the practice (mock) engine.

Run: uv run python examples/quickstart.py
The mock engine is NOT a real TTS; swap in SayEngine("Yuna") on macOS, PiperEngine(...),
or CallableEngine(...) for real audio.
"""

from tts_pace import MockEngine, fit

result = fit(
    "Today we learn how to match the speaking rate of a synthetic voice.",
    target_sps=4.0,
    engine=MockEngine("en"),
    out="quickstart.wav",
)
print(f"path={result.best.path} err={result.best.err_pct:.2f}% (mock engine, route={result.route})")
