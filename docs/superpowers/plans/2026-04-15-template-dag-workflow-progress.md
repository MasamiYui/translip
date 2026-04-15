# Template DAG Workflow Progress

## Completed

### Milestone 1

- Added workflow node registry and template registry:
  - `src/translip/orchestration/nodes.py`
  - `src/translip/orchestration/templates.py`
  - `src/translip/orchestration/graph.py`
- Added deterministic template plan resolution with `required` / `optional` metadata.
- Extended `PipelineRequest` with:
  - `template_id`
  - `delivery_policy`
- Added CLI inputs for:
  - `--template`
  - `--video-source`
  - `--audio-source`
  - `--subtitle-source`
- Added matching server config schema fields.

### Milestone 2

- Refactored pipeline execution from fixed stage sequence to template-resolved node plan execution.
- Preserved compatibility with `run_from_stage` / `run_to_stage` by filtering node execution through sequence hints.
- Added `partial_success` semantics for optional node failures.
- Added workflow manifest/report duplication:
  - legacy: `pipeline-manifest.json`, `pipeline-report.json`
  - new: `workflow-manifest.json`, `workflow-report.json`
- Added workflow graph export helper:
  - `src/translip/orchestration/graph_export.py`
- Added task graph route:
  - `GET /api/tasks/{task_id}/graph`
- Updated task manager to:
  - build `PipelineRequest` with template and delivery policy
  - pre-create task rows from resolved template nodes
  - sync node payloads from `nodes` or legacy `stages`
  - treat `partial_success` as a terminal workflow state

### Milestone 3

- Added OCR detection bridge against the local sibling repo:
  - `src/translip/orchestration/ocr_bridge.py`
  - `scripts/subtitle_ocr_cli_bridge.py`
- Added OCR translation bundle support:
  - `src/translip/subtitles/runner.py`
  - `src/translip/subtitles/export.py`
- Added new `PipelineRequest` inputs for local bridge roots:
  - `ocr_project_root`
  - `erase_project_root`
- Threaded those inputs through:
  - CLI parser
  - request builder
  - server schemas
  - task manager
- Added runner support for:
  - `ocr-detect`
  - `ocr-translate`

### Milestone 4

- Added subtitle erasure bridge against the local sibling repo:
  - `src/translip/orchestration/erase_bridge.py`
- Extended subprocess execution to accept per-stage environment overrides.
- Added delivery source resolution so Task G can choose:
  - original video
  - clean video from `subtitle-erase`
- Verified real subtitle erasure output on sample media and confirmed the rendered frame no longer contains the original hard subtitle.

## Smoke Findings

- OCR detection succeeded on a real sample clip from `test_video/我在迪拜等你.mp4`.
- OCR translation succeeded on the detected events and produced:
  - `ocr_subtitles.en.json`
  - `ocr_subtitles.en.srt`
- Subtitle erasure succeeded on the same clip and produced:
  - `subtitle-erase/clean_video.mp4`
  - `subtitle-erase/subtitle-erase-manifest.json`

### Root Cause Fixed During Smoke

The first subtitle-erasure smoke run failed with:

```text
IndexError: list index out of range
```

Root cause:

- `ffprobe` reported `416` frames for the generated smoke clip
- OpenCV inside the subtitle-erasure runtime could actually read only `176` frames
- the reused `detection.json` was carrying the larger frame count
- subtitle-erasure therefore expanded `context_end` beyond the last readable frame and crashed while indexing `context_frames`

Fix:

- the OCR bridge now computes a conservative `video.total_frames` using the highest frame that OpenCV can actually read
- the bridge also preserves:
  - `reported_total_frames`
  - `readable_total_frames`
  in the debug payload for diagnostics

## Verification Run

The following commands were run after implementation:

```bash
uv run pytest -q tests/test_workflow_graph.py tests/test_cli.py::test_cli_run_pipeline_parser_accepts_template_and_policy tests/test_orchestration.py::test_build_pipeline_request_keeps_template_and_delivery_policy
uv run pytest -q tests/test_cli.py tests/test_orchestration.py
uv run pytest -q tests/test_orchestration.py::test_run_pipeline_executes_nodes_from_template_plan tests/test_orchestration.py::test_run_pipeline_marks_partial_success_when_optional_node_fails
uv run pytest -q tests/test_orchestration.py tests/test_cli.py tests/test_delivery.py
uv run pytest -q tests/test_server_graph.py
uv run pytest -q tests/test_orchestration.py tests/test_cli.py tests/test_delivery.py tests/test_server_graph.py tests/test_server_app.py
uv run pytest -q tests/test_orchestration.py::test_translate_ocr_events_writes_json_and_srt tests/test_delivery.py::test_resolve_delivery_inputs_prefers_clean_video_when_available tests/test_delivery.py::test_resolve_delivery_inputs_falls_back_to_original_video
uv run pytest -q tests/test_workflow_graph.py tests/test_cli.py tests/test_orchestration.py tests/test_delivery.py tests/test_server_graph.py tests/test_server_app.py
```

## Current Status

- Core graph kernel: complete
- Node-plan runner: complete
- Workflow graph payload and route: complete
- OCR detect / OCR translate bridge: complete
- Subtitle erasure bridge: complete
- Frontend workflow graph: not started

## Smoke Commands

The following real-media checks were run from the repo workspace:

```bash
/Users/masamiyui/OpenSoureProjects/Forks/subtitle-ocr/.venv/bin/python scripts/subtitle_ocr_cli_bridge.py --project-root /Users/masamiyui/OpenSoureProjects/Forks/subtitle-ocr --input .codex-runtime/smoke/ocr_smoke_clip_120.mp4 --output-dir .codex-runtime/smoke/ocr-detect-120-fixed --language ch --sample-interval 0.25
uv run python - <<'PY'
from pathlib import Path
from translip.subtitles.runner import translate_ocr_events
translate_ocr_events(
    events_path=Path('.codex-runtime/smoke/ocr-detect-120-fixed/ocr_events.json'),
    output_dir=Path('.codex-runtime/smoke/ocr-translate-120-fixed'),
    target_lang='en',
    backend_name='local-m2m100',
    source_lang='zh',
    device='cpu',
)
PY
uv run python - <<'PY'
from pathlib import Path
from translip.types import PipelineRequest
from translip.orchestration.erase_bridge import run_subtitle_erase

request = PipelineRequest(
    input_path=Path('.codex-runtime/smoke/ocr_smoke_clip_120.mp4').resolve(),
    output_root=Path('.codex-runtime/smoke/workflow120-fixed').resolve(),
    target_lang='en',
    transcription_language='zh',
    ocr_project_root=Path('/Users/masamiyui/OpenSoureProjects/Forks/subtitle-ocr'),
    erase_project_root=Path('/Users/masamiyui/OpenSoureProjects/Forks/video-subtitle-erasure'),
)
run_subtitle_erase(request, log_path=request.output_root / 'logs' / 'subtitle-erase.log')
PY
```

## Next Focus

Move to frontend execution graph work:

1. Implement static workflow subgraph rendering in the frontend
2. Add runtime node-state animation and SSE-driven graph updates
3. Add drill-down drawer for node details, logs, and produced artifacts
4. Run frontend verification against live task graph payloads
