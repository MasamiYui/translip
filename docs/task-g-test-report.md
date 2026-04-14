# Task G Test Report

## Scope

This report validates `Task G`, the final delivery layer that muxes Task E audio
assets back into the original video and exports final `mp4` outputs.

## Automated Tests

Command:

```bash
uv run pytest -q
```

Latest result:

- `47 passed`

Task G-specific automated coverage includes:

- `export-video` CLI parsing
- inferring `input_video_path` and `task_e_dir` from `pipeline-root`
- default output directory resolution
- delivery manifest/report generation
- preview-only export behavior
- mux invocation parameter wiring

## Real Pipeline Validation

Input:

- `test_video/我在迪拜等你.mp4`

### Step 1: Fresh A -> E pipeline run

Command:

```bash
uv run translip run-pipeline \
  --input ./test_video/我在迪拜等你.mp4 \
  --output-root ./tmp/task-g-pipeline-full \
  --target-lang en \
  --write-status
```

Observed result:

- `pipeline status`: `succeeded`
- `task-e placed_count`: `90`
- `task-e skipped_count`: `74`

### Step 2: Task G export

Command:

```bash
uv run translip export-video \
  --pipeline-root ./tmp/task-g-pipeline-full
```

Observed outputs:

- `task-g/delivery/final-preview/final_preview.en.mp4`
- `task-g/delivery/final-dub/final_dub.en.mp4`
- `task-g/delivery/delivery-manifest.json`
- `task-g/delivery/delivery-report.json`

Observed result:

- `delivery status`: `succeeded`
- `exported_count`: `2`
- `failed_count`: `0`

## Media Validation

Both exported `mp4` files were checked with `ffprobe`.

`final_preview.en.mp4`:

- stream 0: `h264` video
- stream 1: `aac` audio
- duration: `534.636364`

`final_dub.en.mp4`:

- stream 0: `h264` video
- stream 1: `aac` audio
- duration: `534.636364`

This matches the expected Task G default behavior:

- preserve the original video stream
- replace the audio track
- keep the exported duration aligned to the source video

## Notes

- Task G is functioning as a pure delivery layer and does not rerun upstream
  stages.
- The dominant runtime in the end-to-end validation remained `Task D`; Task G
  itself completed quickly once Task E artifacts existed.
