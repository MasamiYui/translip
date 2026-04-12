# video-voice-separate

Separate `voice` and `background` audio from local video or audio files, then
build speaker-aware artifacts for downstream dubbing.

## Current Scope

The repository currently contains two working stages:

1. Source separation
  Input local video/audio and output `voice` plus `background`
2. Speaker-aware analysis
  Input `voice` and output speaker-attributed transcript plus file-backed speaker registry artifacts
3. Translation script generation
  Input Task A/B artifacts and output multilingual translation scripts for downstream dubbing
4. Single-speaker target-language synthesis
  Input Task B/C artifacts and output segment-level cloned speech plus Task D evaluation reports

## Quick Start

Install dependencies:

```bash
uv sync
```

### Stage 1: Separate Voice and Background

```bash
uv run video-voice-separate run \
  --input ./test_video/example.mp4 \
  --mode auto \
  --quality balanced \
  --output-dir ./output
```

Download the built-in `CDX23` dialogue checkpoints ahead of time if you plan to use
`--mode dialogue` often:

```bash
uv run video-voice-separate download-models --backend cdx23 --quality balanced
```

Run the dialogue backend explicitly:

```bash
uv run video-voice-separate run \
  --input ./test_video/example.mp4 \
  --mode dialogue \
  --quality balanced \
  --output-dir ./output-dialogue \
  --keep-intermediate
```

### Stage 2A: Speaker-Attributed Transcription

```bash
uv run video-voice-separate transcribe \
  --input ./output/example/voice.mp3 \
  --output-dir ./output-task-a
```

Outputs:

- `segments.zh.json`
- `segments.zh.srt`
- `task-a-manifest.json`

### Stage 2B: Speaker Registry and Retrieval

```bash
uv run video-voice-separate build-speaker-registry \
  --segments ./output-task-a/voice/segments.zh.json \
  --audio ./output/example/voice.mp3 \
  --output-dir ./output-task-b \
  --registry ./output-task-b/registry/speaker_registry.json \
  --update-registry
```

Outputs:

- `speaker_profiles.json`
- `speaker_matches.json`
- `speaker_registry.json`
- `task-b-manifest.json`

### Stage 2C: Translation Script Generation

```bash
uv run video-voice-separate translate-script \
  --segments ./output-task-a/voice/segments.zh.json \
  --profiles ./output-task-b/voice/speaker_profiles.json \
  --target-lang en \
  --backend local-m2m100 \
  --glossary ./config/glossary.example.json \
  --output-dir ./output-task-c
```

Use the SiliconFlow backend through environment variables instead of hardcoding a key:

```bash
export SILICONFLOW_API_KEY=...
uv run video-voice-separate translate-script \
  --segments ./output-task-a/voice/segments.zh.json \
  --profiles ./output-task-b/voice/speaker_profiles.json \
  --target-lang en \
  --backend siliconflow \
  --api-model deepseek-ai/DeepSeek-V3 \
  --glossary ./config/glossary.example.json \
  --output-dir ./output-task-c-api
```

Outputs:

- `translation.<target_tag>.json`
- `translation.<target_tag>.editable.json`
- `translation.<target_tag>.srt`
- `task-c-manifest.json`

### Demo Script: Stage 1 To Task C

```bash
uv run python scripts/run_task_a_to_c.py \
  --input ./test_video/example.mp4 \
  --output-root ./tmp/e2e-task-a-to-c \
  --target-lang en \
  --translation-backend local-m2m100
```

### Stage 2D: Single-Speaker Voice Cloning

`Task D` currently ships with a working `F5-TTS` development backend and an
`OpenVoice V2` placeholder backend interface for later production work.

```bash
uv run video-voice-separate synthesize-speaker \
  --translation ./output-task-c/voice/translation.en.json \
  --profiles ./output-task-b/voice/speaker_profiles.json \
  --speaker-id spk_0001 \
  --output-dir ./output-task-d \
  --backend f5tts \
  --device auto
```

Outputs:

- `speaker_segments.<target_tag>.json`
- `speaker_demo.<target_tag>.wav`
- `task-d-manifest.json`

Notes:

- The first `F5-TTS` run downloads the model checkpoint and vocoder into
  `~/.cache/video-voice-separate/f5-tts/assets/`
- `Task D` is currently tuned for short single-speaker segments, not long
  paragraph-length lines
- `OpenVoice V2` is reserved as the next backend because current work is focused
  on getting the local `MacBook M4 16GB` development path stable first

### Demo Script: Stage 1 To Task D

```bash
uv run python scripts/run_task_a_to_d.py \
  --input ./test_video/example.mp4 \
  --output-root ./tmp/e2e-task-a-to-d \
  --target-lang en \
  --translation-backend local-m2m100 \
  --tts-backend f5tts \
  --max-segments 3
```

## Commands

- `video-voice-separate run`: separate a file into `voice` and `background`
- `video-voice-separate transcribe`: build a speaker-attributed transcript from a voice track
- `video-voice-separate build-speaker-registry`: build speaker profiles and match them against a file-backed registry
- `video-voice-separate translate-script`: generate a translation script for downstream dubbing
- `video-voice-separate synthesize-speaker`: synthesize target-language speech for one speaker and export Task D evaluation artifacts
- `video-voice-separate probe`: inspect input media metadata
- `video-voice-separate download-models`: download backend checkpoints into cache

## Docs

- [docs/README.md](docs/README.md): document index
- [docs/technical-design.md](docs/technical-design.md): source separation system design
- [docs/speaker-aware-dubbing-plan.md](docs/speaker-aware-dubbing-plan.md): overall multi-stage dubbing plan
- [docs/speaker-aware-dubbing-task-breakdown.md](docs/speaker-aware-dubbing-task-breakdown.md): task breakdown
- [docs/task-a-speaker-attributed-transcription.md](docs/task-a-speaker-attributed-transcription.md): Task A design
- [docs/task-a-test-report.md](docs/task-a-test-report.md): Task A validation report
- [docs/task-b-speaker-registry-and-retrieval.md](docs/task-b-speaker-registry-and-retrieval.md): Task B design
- [docs/task-b-test-report.md](docs/task-b-test-report.md): Task B validation report
- [docs/task-c-dubbing-script-generation.md](docs/task-c-dubbing-script-generation.md): Task C design
- [docs/task-c-test-report.md](docs/task-c-test-report.md): Task C validation report
- [docs/task-d-single-speaker-voice-cloning.md](docs/task-d-single-speaker-voice-cloning.md): Task D design
- [docs/task-d-test-report.md](docs/task-d-test-report.md): Task D validation report
