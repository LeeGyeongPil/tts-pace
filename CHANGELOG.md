# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [0.3.0] - 2026-11-11

### Added
- `tts-pace fit --json` prints the report JSON (same structure as `retime --json`) to stdout as a single line.
  The practice-mode `[mock]` notice and warnings go to stderr; errors still exit 2 with an empty stdout.

### Known issues
- Tests for `--json` do not yet cover `--lang` or `--target-duration` with `--cache-dir`.
- On a `--json` error in mock mode, the first stderr line is the `[mock]` notice, followed by the `error:` line (stdout stays empty, exit 2).

### Unchanged
- Without `--json`, output, reports and exit codes are identical to 0.2.0.

## [0.2.0] - 2026-11-11

### Added
- `target_duration` (seconds, total length including pauses) for `fit()` and `fit_audio()`, and
  `--target-duration SECONDS` for `tts-pace fit` and `retime` (mutually exclusive with `--target`).
  Reports gain `target_duration`, `result_total_s` and `length_err_pct` in this mode only.
- `target_sps` may be `None` when `target_duration` is given.

### Known issues
- With `--target-duration 0` (or negative) the `error:` line is followed by the mock-engine banner; exit code is still 2.
- Some length-mode tests assert loosely and are to be tightened.

### Unchanged
- Without the new option, output, reports and cache keys are identical to 0.1.1.

## [0.1.1] - 2026-11-10

### Changed
- README: replaced the feature comparison table with a short "when to use" section (documentation only).

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
