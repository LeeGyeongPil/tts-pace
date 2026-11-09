"""Deterministic result cache: key = hash of everything that changes the output."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path

from .audio import AudioClip

CACHE_VERSION = "1"


def default_cache_dir() -> Path:
    """``$TTS_PACE_CACHE_DIR``, else ``$XDG_CACHE_HOME/tts-pace``, else ``~/.cache/tts-pace``.

    Never inside the current directory, so the cache cannot leak into a git work tree.
    """
    explicit = os.environ.get("TTS_PACE_CACHE_DIR")
    if explicit:
        return Path(explicit).expanduser()
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "tts-pace"


def make_key(parts: dict[str, object]) -> str:
    """sha256 over canonical JSON of ``parts`` (plus the cache format version)."""
    blob = json.dumps({"v": CACHE_VERSION, **parts}, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def audio_hash(clip: AudioClip) -> str:
    """Hash of the audio content (used as the key for engines that are not deterministic)."""
    h = hashlib.sha256()
    h.update(str(clip.sample_rate).encode())
    h.update(clip.samples.tobytes())
    return h.hexdigest()


class ResultCache:
    """Stores the best WAV and the report JSON per key. Oldest entries are removed beyond ``max_entries``."""

    def __init__(self, directory: str | Path, max_entries: int = 256) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be >= 1")
        self.directory = Path(directory)
        self.max_entries = max_entries

    def _paths(self, key: str) -> tuple[Path, Path]:
        return self.directory / f"{key}.json", self.directory / f"{key}.wav"

    def get(self, key: str) -> tuple[dict[str, object], Path] | None:
        report_path, wav_path = self._paths(key)
        if not (report_path.exists() and wav_path.exists()):
            return None
        try:
            return json.loads(report_path.read_text(encoding="utf-8")), wav_path
        except (OSError, ValueError):
            return None  # a damaged entry counts as a miss and is rewritten

    def put(self, key: str, report: dict[str, object], clip: AudioClip) -> Path:
        self.directory.mkdir(parents=True, exist_ok=True)
        report_path, wav_path = self._paths(key)
        tmp_wav = wav_path.with_suffix(".wav.tmp")
        clip.to_wav(tmp_wav)
        os.replace(tmp_wav, wav_path)
        tmp_json = report_path.with_suffix(".json.tmp")
        tmp_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp_json, report_path)  # the json appears last: it marks a complete entry
        self._evict()
        return wav_path

    def _evict(self) -> None:
        entries = sorted(self.directory.glob("*.json"), key=lambda p: p.stat().st_mtime)
        for old in entries[: max(0, len(entries) - self.max_entries)]:
            old.unlink(missing_ok=True)
            old.with_suffix(".wav").unlink(missing_ok=True)

    def copy_wav(self, key: str, dest: str | Path) -> Path:
        d = Path(dest)
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(self._paths(key)[1], d)
        return d
