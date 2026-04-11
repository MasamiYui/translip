# video-voice-separate

Separate `voice` and `background` audio from local video or audio files, then
build speaker-aware artifacts for downstream dubbing.

## Current Scope

The repository currently contains two working stages:

1. Source separation
  Input local video/audio and output `voice` plus `background`
2. Speaker-aware analysis
  Input `voice` and output speaker-attributed transcript plus file-backed speaker registry artifacts

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

## Commands

- `video-voice-separate run`: separate a file into `voice` and `background`
- `video-voice-separate transcribe`: build a speaker-attributed transcript from a voice track
- `video-voice-separate build-speaker-registry`: build speaker profiles and match them against a file-backed registry
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
