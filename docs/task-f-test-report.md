# Task F Test Report

## Scope

This report validates `Task F`, the cache-aware pipeline orchestrator that runs
`stage1 -> task-a -> task-b -> task-c -> task-d -> task-e` through one
`run-pipeline` entry point.

## Automated Tests

Command:

```bash
uv run pytest -q
```

Latest result:

- `44 passed`

Task F-specific coverage includes:

- `run-pipeline` CLI parsing
- JSON config merge with CLI override precedence
- stage sequence resolution
- stage cache hit detection
- pipeline status payload generation
- manifest/report/status file writing
- cache-aware rerun behavior

## Real Pipeline Validation

Input:

- `test_video/我在迪拜等你.mp4`

Command:

```bash
uv run translip run-pipeline \
  --input ./test_video/我在迪拜等你.mp4 \
  --output-root ./tmp/task-f-pipeline-full \
  --target-lang en \
  --write-status
```

Observed outputs:

- `request.json`
- `pipeline-status.json`
- `pipeline-manifest.json`
- `pipeline-report.json`
- `stage1/我在迪拜等你/{voice.mp3,background.mp3,manifest.json}`
- `task-a/voice/{segments.zh.json,segments.zh.srt,task-a-manifest.json}`
- `task-b/voice/{speaker_profiles.json,speaker_matches.json,task-b-manifest.json}`
- `task-c/voice/{translation.en.json,translation.en.editable.json,translation.en.srt,task-c-manifest.json}`
- `task-d/task-d-stage-manifest.json`
- `task-e/voice/{dub_voice.en.wav,preview_mix.en.wav,timeline.en.json,mix_report.en.json,task-e-manifest.json}`

Primary result:

- `pipeline status`: `succeeded`
- `task-e placed_count`: `90`
- `task-e skipped_count`: `74`

## Cache Validation

Command:

```bash
uv run translip run-pipeline \
  --input ./test_video/我在迪拜等你.mp4 \
  --output-root ./tmp/task-f-pipeline-full \
  --target-lang en \
  --write-status
```

Observed result:

- all six stages returned `status=cached`
- `pipeline-report.json` reported `cached_count=6`
- `pipeline-status.json` finished with all stage rows marked `cached`

## Notes

- The orchestrator is functioning as intended for full local runs.
- The dominant runtime remains `Task D`, not the orchestration layer.
- Current status tracking is stage-level plus speaker-level for `Task D`; it is
  intentionally simple and does not yet expose segment-level progress.
