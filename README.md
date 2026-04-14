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
5. Multi-speaker timeline fitting and preview mixing
  Input Task A/C/D artifacts plus stage 1 background and output dub voice plus preview mix
6. Pipeline orchestration
  Input one source file and orchestrate stage 1 through Task E with cache-aware execution and status tracking
7. Final video delivery
  Input Task E audio assets plus the original video and export final delivery mp4 files

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

`Task D` now uses a single local backend: `Qwen3-TTS-12Hz-0.6B-Base`.

```bash
uv run video-voice-separate synthesize-speaker \
  --translation ./output-task-c/voice/translation.en.json \
  --profiles ./output-task-b/voice/speaker_profiles.json \
  --speaker-id spk_0001 \
  --output-dir ./output-task-d \
  --backend qwen3tts \
  --device auto
```

Outputs:

- `speaker_segments.<target_tag>.json`
- `speaker_demo.<target_tag>.wav`
- `task-d-manifest.json`

Notes:

- The first `Qwen3-TTS` run downloads checkpoints into the Hugging Face cache
- `Task D` uses `non_streaming_mode=True` and a duration-budget-derived
  `max_new_tokens` cap to avoid runaway generation on repetitive lines
- The `run_task_a_to_d.py` and `run_task_a_to_e.py` demo scripts execute each
  stage in a separate subprocess so large local models do not accumulate in one
  Python process on `MacBook M4 16GB`

### Demo Script: Stage 1 To Task D

```bash
uv run python scripts/run_task_a_to_d.py \
  --input ./test_video/example.mp4 \
  --output-root ./tmp/e2e-task-a-to-d \
  --target-lang en \
  --translation-backend local-m2m100 \
  --tts-backend qwen3tts \
  --max-segments 3
```

### Stage 2E: Timeline Fitting And Preview Mixing

```bash
uv run video-voice-separate render-dub \
  --background ./output/example/background.mp3 \
  --segments ./output-task-a/voice/segments.zh.json \
  --translation ./output-task-c/voice/translation.en.json \
  --task-d-report ./output-task-d/voice/spk_0001/speaker_segments.en.json \
  --task-d-report ./output-task-d/voice/spk_0005/speaker_segments.en.json \
  --output-dir ./output-task-e \
  --fit-policy conservative \
  --fit-backend atempo \
  --mix-profile preview \
  --ducking-mode static
```

Outputs:

- `dub_voice.<target_tag>.wav`
- `preview_mix.<target_tag>.wav`
- `timeline.<target_tag>.json`
- `mix_report.<target_tag>.json`
- `task-e-manifest.json`

Notes:

- `Task E` now keeps `Task D overall_status=failed` segments in the timeline as
  long as the generated audio exists; later optimization can still replace or
  suppress them
- `Task E` also keeps overlong or undersized segments instead of dropping them
  at fit time; these are marked as `overflow_unfitted` or `underflow_unfitted`
  in the timeline and mix report
- `--fit-backend rubberband` is exposed as an optional higher-quality path, but
  requires an `ffmpeg` build with the `rubberband` filter
- The default `atempo` backend is the stable local baseline on `MacBook M4 16GB`

### Demo Script: Stage 1 To Task E

```bash
uv run python scripts/run_task_a_to_e.py \
  --input ./test_video/example.mp4 \
  --output-root ./tmp/e2e-task-a-to-e \
  --target-lang en \
  --translation-backend local-m2m100 \
  --tts-backend qwen3tts \
  --speaker-limit 2 \
  --segments-per-speaker 3
```

### Task F: Pipeline Orchestration

```bash
uv run video-voice-separate run-pipeline \
  --input ./test_video/example.mp4 \
  --output-root ./output-pipeline \
  --target-lang en \
  --write-status
```

Outputs:

- `request.json`
- `pipeline-status.json`
- `pipeline-manifest.json`
- `pipeline-report.json`
- all stage directories from `stage1` through `task-e`

Notes:

- `run-pipeline` is cache-aware; rerunning the same command on the same
  `--output-root` reuses successful stage outputs when cache keys still match
- `pipeline-status.json` is updated while the pipeline runs and summarizes
  overall progress plus per-stage status
- `Task D` is the dominant runtime cost in a full local run because it executes
  segment-level TTS and backread evaluation across multiple speakers

### Task G: Final Video Delivery

```bash
uv run video-voice-separate export-video \
  --pipeline-root ./output-pipeline
```

Outputs:

- `final-preview/final_preview.<target_tag>.mp4`
- `final-dub/final_dub.<target_tag>.mp4`
- `delivery-manifest.json`
- `delivery-report.json`

Notes:

- `export-video` consumes Task E outputs and does not rerun upstream stages
- By default it preserves the original video stream and re-encodes only the
  output audio track as `aac`
- The default end policy is `trim_audio_to_video`, which keeps the exported
  video aligned to the original video duration

## Commands

- `video-voice-separate run`: separate a file into `voice` and `background`
- `video-voice-separate transcribe`: build a speaker-attributed transcript from a voice track
- `video-voice-separate build-speaker-registry`: build speaker profiles and match them against a file-backed registry
- `video-voice-separate translate-script`: generate a translation script for downstream dubbing
- `video-voice-separate synthesize-speaker`: synthesize target-language speech for one speaker and export Task D evaluation artifacts
- `video-voice-separate render-dub`: assemble Task D speaker outputs into a Task E dub timeline and preview mix
- `video-voice-separate run-pipeline`: orchestrate stage 1 through Task E with cache-aware execution and pipeline status output
- `video-voice-separate export-video`: mux Task E audio assets back into the source video and export final delivery mp4 files
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
- [docs/task-e-timeline-fitting-and-mixing.md](docs/task-e-timeline-fitting-and-mixing.md): Task E design
- [docs/task-e-test-report.md](docs/task-e-test-report.md): Task E validation report
- [docs/task-f-pipeline-and-engineering-orchestration.md](docs/task-f-pipeline-and-engineering-orchestration.md): Task F design
- [docs/task-f-test-report.md](docs/task-f-test-report.md): Task F validation report
- [docs/task-g-final-video-delivery.md](docs/task-g-final-video-delivery.md): Task G design
- [docs/task-g-test-report.md](docs/task-g-test-report.md): Task G validation report
