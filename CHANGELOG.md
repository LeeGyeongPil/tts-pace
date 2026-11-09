# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [0.1.0] - 2026-11-09

### Added
- Syllable counting for Korean (blocks), English (vowel-group heuristic plus a small exception
  dictionary) and Japanese (morae), with spoken-form normalization of numbers and acronyms.
- Articulation-rate measurement: syllables divided by speech time without long silences
  (numpy backend, optional ffmpeg `silencedetect` backend).
- Pitch-preserving tempo change limited to 0.85-1.15 (numpy WSOLA, optional ffmpeg `atempo`).
- Closed-loop `fit()` and engine-free `fit_audio()` with warnings `knob_response_weak`,
  `knob_clamped`, `tempo_clamped`, `unsupported_chars`.
- Deterministic result cache with an entry limit.
- Engine adapters: `MockEngine` (practice engine, not a real TTS), `CallableEngine`, `SayEngine`,
  `PiperEngine`.
- Concurrency `Limiter`, per-run temp folders, subprocess timeouts.
- `tts-pace` CLI: `demo`, `count`, `measure`, `retime`, `fit`.
