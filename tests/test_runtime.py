import sys
import tempfile
import threading
from pathlib import Path

import pytest

from tts_pace import BusyError, CallableEngine, EngineError, Limiter, fit
from tts_pace.runtime import run_command, run_dir


def test_temp_folder_is_removed_when_the_engine_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    seen = []

    def broken(text, speed):
        seen.append([p.name for p in tmp_path.iterdir()])  # the run folder exists while we work
        raise RuntimeError("engine crashed")

    with pytest.raises(RuntimeError, match="engine crashed"):
        fit("hello there my friend", 4.0, CallableEngine(broken), cache_dir=False)
    assert seen and seen[0][0].startswith("tts-pace-")
    assert list(tmp_path.iterdir()) == []


def test_run_dir_cleans_up_on_error(tmp_path, monkeypatch):
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    with pytest.raises(KeyError), run_dir() as d:
        (d / "f").write_text("x")
        raise KeyError("boom")
    assert not any(tmp_path.iterdir())


def test_second_concurrent_request_gets_busy_immediately():
    limiter = Limiter(max_concurrent=1, max_waiting=0)
    entered, release = threading.Event(), threading.Event()

    def hold():
        with limiter.slot():
            entered.set()
            release.wait(5)

    t = threading.Thread(target=hold)
    t.start()
    try:
        assert entered.wait(5)
        with pytest.raises(BusyError, match="busy"), limiter.slot():
            pass
    finally:
        release.set()
        t.join()
    with limiter.slot():  # the slot is free again afterwards
        pass


def test_waiting_room_lets_a_request_through_when_a_slot_frees():
    limiter = Limiter(max_concurrent=1, max_waiting=1)
    order = []
    release = threading.Event()

    def first():
        with limiter.slot():
            order.append("first")
            release.wait(5)

    t = threading.Thread(target=first)
    t.start()
    while not order:
        pass
    threading.Timer(0.1, release.set).start()
    with limiter.slot():
        order.append("second")
    t.join()
    assert order == ["first", "second"]


def test_limiter_argument_validation():
    with pytest.raises(ValueError):
        Limiter(max_concurrent=0)
    with pytest.raises(ValueError):
        Limiter(max_waiting=-1)


def test_subprocess_timeout_becomes_engine_error():
    with pytest.raises(EngineError, match="did not finish within"):
        run_command([sys.executable, "-c", "import time; time.sleep(5)"], timeout=0.3)


def test_subprocess_failures_become_engine_errors(tmp_path: Path):
    with pytest.raises(EngineError, match="not found"):
        run_command([str(tmp_path / "no-such-program")])
    with pytest.raises(EngineError, match="exited with code 3"):
        run_command([sys.executable, "-c", "import sys; sys.exit(3)"])
