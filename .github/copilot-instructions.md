# Project Guidelines

## Overview

Speaker-aware multilingual video dubbing pipeline (Python 3.11–3.12). Separates voice/background audio, transcribes with speaker attribution, translates, clones voices, and re-mixes into a final dubbed video.

Pipeline stages: Stage 1 (separation) → Task A (transcription) → Task B (speaker registry) → Task C (translation) → Task D (voice cloning) → Task E (timeline fitting & mixing) → Task F (orchestration) → Task G (video delivery).

## Build and Test

Package manager: **uv**. Build backend: hatchling.

```sh
uv sync                  # Install all dependencies
uv run pytest tests/     # Run test suite
uv run video-voice-separate --help   # CLI entry point
```

No linter/formatter config is enforced — no ruff, black, or mypy configuration exists.

## Architecture

Each pipeline stage lives in its own module under `src/video_voice_separate/`:

| Module | Stage | Purpose |
|--------|-------|---------|
| `pipeline/` | Stage 1 | Voice/background separation (Demucs for music, CDX23 for dialogue) |
| `transcription/` | Task A | ASR via faster-whisper, speaker diarization |
| `speakers/` | Task B | Speaker embeddings (SpeechBrain ECAPA), registry, profile matching |
| `translation/` | Task C | M2M100 local or SiliconFlow API, glossary support |
| `dubbing/` | Task D | Qwen TTS voice cloning |
| `rendering/` | Task E | Timeline fitting, audio mixing, ducking |
| `delivery/` | Task G | FFmpeg video muxing, final MP4 export |
| `orchestration/` | Task F | Cache-aware multi-stage pipeline runner |
| `models/` | — | Model backends (DemucsMusicSeparator, Cdx23DialogueSeparator) |

Entry points: `cli.py` → dispatches to each module's `runner.py`.

See [docs/](../docs/README.md) for detailed design docs per task.

## Conventions

### Request/Result pattern

Every task follows the same shape:
- **Request** dataclass (`@dataclass(slots=True)`) with a `.normalized()` method that resolves paths
- **Result** dataclass with status, artifacts, manifest path, error tracking
- **Runner** function that takes a Request → returns a Result
- **Export** module that builds JSON manifests

### Code style

- `from __future__ import annotations` at the top of every file
- Relative imports within the package: `from ..config import ...`
- `Path` objects (pathlib) for all file paths, accepted as `Path | str`
- `logger = logging.getLogger(__name__)` per module
- Constants in `config.py` as `UPPER_SNAKE_CASE`
- Private helpers prefixed with `_`

### JSON & timestamps

- Read: `json.loads(path.read_text(encoding="utf-8"))`
- Write: `json.dumps(..., ensure_ascii=False, indent=2)`
- Timestamps: `now_iso()` for ISO 8601, `time.monotonic()` for elapsed

### Error handling

- Custom hierarchy rooted at `VideoVoiceSeparateError(RuntimeError)` in `exceptions.py`
- Subclasses: `DependencyError`, `FFmpegError`, `BackendUnavailableError`
- Runners catch errors and write error payloads to manifests

### Testing

- pytest with `tmp_path` for file I/O
- Monkeypatch external tools (FFmpeg, model loading) — do not call real models in unit tests
- Test naming: `test_<function>_<expected_behavior>()`
- Build minimal stub fixtures (JSON payloads, numpy arrays)

### FFmpeg

All FFmpeg interaction goes through `utils/ffmpeg.py` helpers (`probe_media`, `render_wav`, `mux_video_with_audio`). Never call FFmpeg directly.

## Key Config

Defaults live in `src/video_voice_separate/config.py`. Notable:
- `DEFAULT_SAMPLE_RATE = 44_100`, transcription at `16_000`
- Device auto-detection: CPU/CUDA/MPS
- Cache: `~/.cache/video-voice-separate` (override with `VIDEO_VOICE_SEPARATE_CACHE_DIR`)
- HuggingFace: `HF_HUB_DISABLE_XET=1` set at import time

## CLI Subcommands

`run`, `transcribe`, `build-speaker-registry`, `translate-script`, `synthesize-speaker`, `render-dub`, `export-video`, `run-pipeline`, `probe`, `download-models`

See root [README.md](../README.md) for usage examples.
