# OCR Guided ASR Correction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an OCR-guided ASR correction node that keeps ASR timing and speaker labels while using high-confidence hard-subtitle OCR text to correct the Chinese script used for dubbing and translation.

**Architecture:** Implement a focused transcription correction module, expose it through a CLI command and a `transcript-correction` atomic tool, insert a new `asr-ocr-correct` workflow node between `task-a`/`ocr-detect` and downstream dubbing nodes, and route all downstream segment consumers through one effective segment path resolver. The frontend defaults correction to enabled with the standard preset and shows a compact explanation plus correction summary.

**Tech Stack:** Python dataclasses, FastAPI/Pydantic, existing workflow graph/orchestration modules, React 19, TypeScript, Vitest, pytest.

---

## File Structure

- Create `src/translip/transcription/ocr_correction.py`
  - Owns correction config, OCR event loading, ASR/OCR alignment, correction decisions, report generation, and writing corrected segment artifacts.
- Modify `src/translip/transcription/__init__.py`
  - Exports correction entry points if the package currently exposes task-level helpers.
- Modify `src/translip/cli.py`
  - Adds `correct-asr-with-ocr` CLI command.
- Modify `src/translip/types.py`
  - Adds workflow node literal `asr-ocr-correct`, correction preset/config types, and `PipelineRequest.transcription_correction`.
- Modify `src/translip/orchestration/commands.py`
  - Adds correction artifact path helpers, `effective_task_a_segments_path`, and `build_asr_ocr_correction_command`.
- Modify `src/translip/orchestration/runner.py`
  - Adds cache payload/artifacts for `asr-ocr-correct`, executes the new node, and uses effective segments in final artifacts.
- Modify `src/translip/orchestration/stages.py`
  - Adds `asr-ocr-correct` to legacy stage ordering for explicit reruns and developer controls.
- Modify `src/translip/orchestration/nodes.py`
  - Registers `asr-ocr-correct`.
- Modify `src/translip/orchestration/templates.py`
  - Adds the node to OCR templates and expresses OCR-template dependency overrides.
- Modify `src/translip/orchestration/graph.py`
  - Supports template-specific dependency overrides so `task-b` depends on `asr-ocr-correct` only in OCR templates.
- Modify `src/translip/orchestration/graph_export.py`
  - Emits edges from the resolved plan rather than directly from global node definitions.
- Modify `src/translip/server/task_config.py`
  - Adds default `transcription_correction` config under pipeline settings.
- Modify `src/translip/server/schemas.py`
  - Adds the task config input shape and read-model summary fields.
- Modify `src/translip/server/task_manager.py`
  - Maps stored correction config into `PipelineRequest`.
- Modify `src/translip/server/task_read_model.py`
  - Surfaces correction summary from `correction-report.json`.
- Modify `src/translip/server/atomic_tools/schemas.py`
  - Adds `TranscriptCorrectionToolRequest` with ASR segments input, OCR events input, preset, enabled flag, and OCR-only policy.
- Create `src/translip/server/atomic_tools/adapters/transcript_correction.py`
  - Exposes the shared OCR correction module as an independent atomic tool.
- Modify `src/translip/server/atomic_tools/adapters/__init__.py`
  - Imports `TranscriptCorrectionAdapter` so registration happens at package import.
- Modify `frontend/src/types/index.ts`
  - Adds correction config and correction summary types.
- Modify `frontend/src/pages/NewTaskPage.tsx`
  - Defaults OCR-capable tasks to correction enabled + standard preset and shows the hidden explanation.
- Modify `frontend/src/pages/TaskDetailPage.tsx`
  - Shows correction summary when available.
- Modify `frontend/src/lib/workflowPreview.ts`
  - Adds `asr-ocr-correct` to OCR template previews and edges.
- Modify `frontend/src/i18n/formatters.ts`
  - Adds `asr-ocr-correct` to developer stage options.
- Modify `frontend/src/i18n/messages.ts`
  - Adds localized stage labels for `asr-ocr-correct`.
- Add `tests/test_asr_ocr_correction.py`
  - Unit coverage for correction algorithm and artifact writing.
- Modify `tests/test_cli.py`
  - CLI parser coverage.
- Modify `tests/test_workflow_graph.py`
  - Workflow order and dependency edge coverage.
- Modify `tests/test_orchestration.py`
  - Command path, cache, and effective segment path coverage.
- Modify `tests/test_task_config_normalization.py`
  - Correction config default and request mapping coverage.
- Modify `tests/test_task_read_models.py`
  - Read-model correction summary coverage.
- Modify `tests/test_atomic_tools_registry.py`
  - Verifies `transcript-correction` is registered without changing existing tool categories.
- Add `tests/test_atomic_tools_adapters/test_transcript_correction_adapter.py`
  - Adapter request validation, artifact copying, and summary coverage.
- Modify `frontend/src/pages/__tests__/NewTaskPage.test.tsx`
  - UI default and hidden explanation coverage.
- Modify `frontend/src/pages/__tests__/TaskDetailPage.delivery.test.tsx`
  - Correction summary display coverage.

## Implementation Notes

- Do not add a global “is this video suitable for correction” precheck in V1.
- Do not auto-insert OCR-only text into corrected segments.
- Do not expose every threshold as first-level UI. Keep only enabled + preset visible, with a hidden explanation and developer-level config.
- Do not route downstream nodes directly to `task-a/voice/segments.zh.json` after this change. Use `effective_task_a_segments_path(request)`.
- Keep glossary ordering unchanged: `ASR -> OCR corrected Chinese -> glossary preprocessing -> translation`.
- Do not change the default semantics of the existing `transcription` atomic tool. It remains raw ASR.
- Add `transcript-correction` as a separate atomic tool that consumes existing ASR/OCR artifacts and reuses the same correction module as the workflow node.

---

### Task 1: Add the OCR Correction Algorithm and Tests

**Files:**
- Create: `src/translip/transcription/ocr_correction.py`
- Modify: `src/translip/transcription/__init__.py`
- Add: `tests/test_asr_ocr_correction.py`

- [ ] **Step 1: Write failing tests for correction decisions**

Add `tests/test_asr_ocr_correction.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from translip.transcription.ocr_correction import (
    CorrectionConfig,
    correct_asr_segments_with_ocr,
)


def _segments_payload() -> dict:
    return {
        "input": {"path": "voice.mp3"},
        "model": {"asr_backend": "faster-whisper"},
        "stats": {"segment_count": 4, "speaker_count": 2},
        "segments": [
            {
                "id": "seg-0001",
                "start": 0.21,
                "end": 2.81,
                "duration": 2.6,
                "speaker_label": "SPEAKER_00",
                "text": "虽扛下了天洁",
                "language": "zh",
            },
            {
                "id": "seg-0002",
                "start": 5.01,
                "end": 10.01,
                "duration": 5.0,
                "speaker_label": "SPEAKER_00",
                "text": "为师现在就为你们重塑肉身",
                "language": "zh",
            },
            {
                "id": "seg-0003",
                "start": 18.11,
                "end": 20.11,
                "duration": 2.0,
                "speaker_label": "SPEAKER_00",
                "text": "头发龙祖",
                "language": "zh",
            },
            {
                "id": "seg-0004",
                "start": 87.88,
                "end": 93.05,
                "duration": 5.17,
                "speaker_label": "SPEAKER_01",
                "text": "小燕拭摩",
                "language": "zh",
            },
        ],
    }


def _ocr_payload() -> dict:
    return {
        "events": [
            {"event_id": "evt-0001", "start": 0.75, "end": 2.50, "text": "虽扛下了天劫", "confidence": 0.996},
            {"event_id": "evt-0002", "start": 5.25, "end": 6.75, "text": "为师现在就为你们", "confidence": 0.999},
            {"event_id": "evt-0003", "start": 7.25, "end": 8.00, "text": "重塑", "confidence": 0.999},
            {"event_id": "evt-0004", "start": 8.75, "end": 9.50, "text": "肉身", "confidence": 0.999},
            {"event_id": "evt-0005", "start": 18.50, "end": 19.75, "text": "讨伐龙族", "confidence": 0.999},
            {"event_id": "evt-0006", "start": 91.75, "end": 92.25, "text": "小爷是魔", "confidence": 0.999},
            {"event_id": "evt-0007", "start": 93.25, "end": 94.00, "text": "那又如何", "confidence": 0.999},
        ]
    }


def test_correct_asr_segments_uses_single_and_merged_ocr_text() -> None:
    result = correct_asr_segments_with_ocr(
        segments_payload=_segments_payload(),
        ocr_payload=_ocr_payload(),
        config=CorrectionConfig.standard(),
    )

    texts = [row["text"] for row in result.corrected_payload["segments"]]
    assert texts == ["虽扛下了天劫", "为师现在就为你们重塑肉身", "讨伐龙族", "小爷是魔"]
    decisions = {row["segment_id"]: row["decision"] for row in result.report["segments"]}
    assert decisions["seg-0001"] == "use_ocr"
    assert decisions["seg-0002"] == "merge_ocr"
    assert decisions["seg-0003"] == "use_ocr"
    assert decisions["seg-0004"] == "use_ocr"
    assert result.report["summary"]["corrected_count"] == 4
    assert result.report["summary"]["algorithm_version"] == "ocr-guided-asr-correction-v1"


def test_ocr_only_event_is_reported_without_inserting_segment() -> None:
    result = correct_asr_segments_with_ocr(
        segments_payload=_segments_payload(),
        ocr_payload=_ocr_payload(),
        config=CorrectionConfig.standard(),
    )

    assert len(result.corrected_payload["segments"]) == 4
    assert result.report["ocr_only_events"] == [
        {
            "event_id": "evt-0007",
            "start": 93.25,
            "end": 94.0,
            "text": "那又如何",
            "decision": "ocr_only",
            "action": "reported_only",
            "needs_review": True,
        }
    ]


def test_low_confidence_ocr_keeps_asr() -> None:
    payload = _ocr_payload()
    payload["events"][0]["confidence"] = 0.1

    result = correct_asr_segments_with_ocr(
        segments_payload=_segments_payload(),
        ocr_payload=payload,
        config=CorrectionConfig.standard(),
    )

    assert result.corrected_payload["segments"][0]["text"] == "虽扛下了天洁"
    assert result.report["segments"][0]["decision"] == "use_asr"
    assert result.report["segments"][0]["needs_review"] is False


def test_write_correction_artifacts(tmp_path: Path) -> None:
    from translip.transcription.ocr_correction import write_correction_artifacts

    result = correct_asr_segments_with_ocr(
        segments_payload=_segments_payload(),
        ocr_payload=_ocr_payload(),
        config=CorrectionConfig.standard(),
    )

    artifacts = write_correction_artifacts(result, output_dir=tmp_path / "asr-ocr-correct" / "voice")

    assert artifacts.corrected_segments_path.exists()
    assert artifacts.corrected_srt_path.exists()
    assert artifacts.report_path.exists()
    assert artifacts.manifest_path.exists()
    manifest = json.loads(artifacts.manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "succeeded"
    assert manifest["config"]["preset"] == "standard"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest -q tests/test_asr_ocr_correction.py
```

Expected: FAIL because `translip.transcription.ocr_correction` does not exist.

- [ ] **Step 3: Implement the correction module**

Create `src/translip/transcription/ocr_correction.py` with these public names:

```python
ALGORITHM_VERSION = "ocr-guided-asr-correction-v1"


def load_json_payload(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


@dataclass(frozen=True, slots=True)
class CorrectionConfig:
    enabled: bool = True
    preset: str = "standard"
    min_ocr_confidence: float = 0.85
    min_alignment_score: float = 0.55
    lead_tolerance_sec: float = 0.6
    lag_tolerance_sec: float = 0.8
    min_length_ratio: float = 0.45
    max_length_ratio: float = 2.2
    ocr_only_policy: str = "report_only"
    algorithm_version: str = ALGORITHM_VERSION

    @classmethod
    def standard(cls) -> "CorrectionConfig":
        return cls()

    @classmethod
    def conservative(cls) -> "CorrectionConfig":
        return cls(preset="conservative", min_ocr_confidence=0.92, min_alignment_score=0.70, min_length_ratio=0.65, max_length_ratio=1.60)

    @classmethod
    def aggressive(cls) -> "CorrectionConfig":
        return cls(preset="aggressive", min_ocr_confidence=0.75, min_alignment_score=0.40, min_length_ratio=0.35, max_length_ratio=2.80)


@dataclass(frozen=True, slots=True)
class CorrectionResult:
    corrected_payload: dict[str, Any]
    report: dict[str, Any]


@dataclass(frozen=True, slots=True)
class CorrectionArtifacts:
    corrected_segments_path: Path
    corrected_srt_path: Path
    report_path: Path
    manifest_path: Path
```

Implementation requirements:

- Normalize ASR text by removing `[SPEAKER_00]` prefixes only when reading SRT-style text. JSON segments already store clean text.
- Use OCR events with `confidence >= min_ocr_confidence`.
- For each ASR segment, collect OCR events that overlap the segment or whose midpoint lands inside the segment.
- Compute `alignment_score` as `min(1.0, total_overlap / max(0.001, asr_duration))`.
- Merge candidate OCR events in start-time order.
- Compute `length_ratio` after removing whitespace and punctuation.
- Replace text when alignment, confidence, and length checks pass.
- Report OCR-only events whose midpoint does not fall inside any ASR segment and which were not used.
- Add top-level `correction` metadata to the corrected payload.
- Write SRT with ASR start/end and corrected text.

- [ ] **Step 4: Export the module from the package**

If `src/translip/transcription/__init__.py` exports task helpers, add:

```python
from .ocr_correction import CorrectionConfig, correct_asr_segments_with_ocr, write_correction_artifacts

__all__ = [
    "CorrectionConfig",
    "correct_asr_segments_with_ocr",
    "write_correction_artifacts",
]
```

If the file is empty and the repo does not use package exports, leave it untouched.

- [ ] **Step 5: Run tests to verify they pass**

Run:

```bash
uv run pytest -q tests/test_asr_ocr_correction.py
```

Expected: PASS.

---

### Task 2: Add CLI Command and Effective Segment Paths

**Files:**
- Modify: `src/translip/cli.py`
- Modify: `src/translip/orchestration/commands.py`
- Modify: `src/translip/types.py`
- Modify: `tests/test_cli.py`
- Modify: `tests/test_orchestration.py`

- [ ] **Step 1: Add failing CLI parser tests**

In `tests/test_cli.py`, add:

```python
def test_parse_correct_asr_with_ocr_command() -> None:
    from translip.cli import build_parser

    parser = build_parser()
    args = parser.parse_args(
        [
            "correct-asr-with-ocr",
            "--segments",
            "task-a/voice/segments.zh.json",
            "--ocr-events",
            "ocr-detect/ocr_events.json",
            "--output-dir",
            "asr-ocr-correct",
            "--preset",
            "standard",
        ]
    )

    assert args.command == "correct-asr-with-ocr"
    assert args.segments == "task-a/voice/segments.zh.json"
    assert args.ocr_events == "ocr-detect/ocr_events.json"
    assert args.output_dir == "asr-ocr-correct"
    assert args.preset == "standard"
```

In `tests/test_orchestration.py`, add:

```python
def test_effective_task_a_segments_prefers_corrected_segments(tmp_path: Path) -> None:
    from translip.orchestration.commands import (
        effective_task_a_segments_path,
        task_a_segments_path,
        task_a_corrected_segments_path,
    )
    from translip.types import PipelineRequest

    request = PipelineRequest(input_path=tmp_path / "sample.mp4", output_root=tmp_path / "out")
    original = task_a_segments_path(request)
    corrected = task_a_corrected_segments_path(request)
    original.parent.mkdir(parents=True)
    original.write_text("{}", encoding="utf-8")
    corrected.parent.mkdir(parents=True)
    corrected.write_text("{}", encoding="utf-8")

    assert effective_task_a_segments_path(request) == corrected


def test_effective_task_a_segments_falls_back_to_original(tmp_path: Path) -> None:
    from translip.orchestration.commands import effective_task_a_segments_path, task_a_segments_path
    from translip.types import PipelineRequest

    request = PipelineRequest(input_path=tmp_path / "sample.mp4", output_root=tmp_path / "out")
    original = task_a_segments_path(request)

    assert effective_task_a_segments_path(request) == original
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest -q tests/test_cli.py::test_parse_correct_asr_with_ocr_command tests/test_orchestration.py::test_effective_task_a_segments_prefers_corrected_segments tests/test_orchestration.py::test_effective_task_a_segments_falls_back_to_original
```

Expected: FAIL because the command and helpers do not exist.

- [ ] **Step 3: Add correction config to `PipelineRequest`**

In `src/translip/types.py`, add:

```python
CorrectionPreset = Literal["conservative", "standard", "aggressive"]


class TranscriptionCorrectionConfig(TypedDict, total=False):
    enabled: bool
    preset: CorrectionPreset
    min_ocr_confidence: float
    min_alignment_score: float
    lead_tolerance_sec: float
    lag_tolerance_sec: float
    min_length_ratio: float
    max_length_ratio: float
    ocr_only_policy: Literal["report_only"]
    llm_arbitration: Literal["off"]
```

Add this field to `PipelineRequest`:

```python
transcription_correction: TranscriptionCorrectionConfig = field(
    default_factory=lambda: cast(
        TranscriptionCorrectionConfig,
        {
            "enabled": True,
            "preset": "standard",
            "ocr_only_policy": "report_only",
            "llm_arbitration": "off",
        },
    )
)
```

Copy it in `PipelineRequest.normalized()`:

```python
transcription_correction=cast(TranscriptionCorrectionConfig, dict(self.transcription_correction)),
```

- [ ] **Step 4: Add path helpers and command builder**

In `src/translip/orchestration/commands.py`, add:

```python
def task_a_correction_bundle_dir(request: PipelineRequest) -> Path:
    return request.output_root / "asr-ocr-correct" / "voice"


def task_a_corrected_segments_path(request: PipelineRequest) -> Path:
    return task_a_correction_bundle_dir(request) / "segments.zh.corrected.json"


def task_a_corrected_srt_path(request: PipelineRequest) -> Path:
    return task_a_correction_bundle_dir(request) / "segments.zh.corrected.srt"


def task_a_correction_report_path(request: PipelineRequest) -> Path:
    return task_a_correction_bundle_dir(request) / "correction-report.json"


def task_a_correction_manifest_path(request: PipelineRequest) -> Path:
    return task_a_correction_bundle_dir(request) / "correction-manifest.json"


def effective_task_a_segments_path(request: PipelineRequest) -> Path:
    corrected = task_a_corrected_segments_path(request)
    return corrected if corrected.exists() else task_a_segments_path(request)
```

Add:

```python
def build_asr_ocr_correction_command(request: PipelineRequest) -> list[str]:
    config = request.transcription_correction
    command = [
        *_cli_prefix(),
        "correct-asr-with-ocr",
        "--segments",
        str(task_a_segments_path(request)),
        "--ocr-events",
        str(request.output_root / "ocr-detect" / "ocr_events.json"),
        "--output-dir",
        str(request.output_root / "asr-ocr-correct"),
        "--preset",
        str(config.get("preset", "standard")),
    ]
    if config.get("enabled", True) is False:
        command.append("--disabled")
    return command
```

Update `build_task_b_command`, `build_task_c_command`, and `build_task_e_command` so all `--segments` arguments use `effective_task_a_segments_path(request)`.

- [ ] **Step 5: Add CLI command execution**

In `src/translip/cli.py`, add parser:

```python
correction_parser = subparsers.add_parser(
    "correct-asr-with-ocr",
    help="Correct ASR transcript text with OCR subtitle events while preserving ASR timing",
)
correction_parser.add_argument("--segments", required=True)
correction_parser.add_argument("--ocr-events", required=True)
correction_parser.add_argument("--output-dir", default="asr-ocr-correct")
correction_parser.add_argument("--preset", default="standard", choices=["conservative", "standard", "aggressive"])
correction_parser.add_argument("--disabled", action="store_true")
```

In `main`, add:

```python
if args.command == "correct-asr-with-ocr":
    from .transcription.ocr_correction import (
        CorrectionConfig,
        correct_asr_segments_with_ocr,
        load_json_payload,
        write_correction_artifacts,
    )

    preset_map = {
        "conservative": CorrectionConfig.conservative,
        "standard": CorrectionConfig.standard,
        "aggressive": CorrectionConfig.aggressive,
    }
    config = preset_map[args.preset]()
    if args.disabled:
        config = CorrectionConfig(enabled=False, preset=args.preset)
    result = correct_asr_segments_with_ocr(
        segments_payload=load_json_payload(Path(args.segments)),
        ocr_payload=load_json_payload(Path(args.ocr_events)),
        config=config,
    )
    artifacts = write_correction_artifacts(result, output_dir=Path(args.output_dir) / "voice")
    print(f"corrected_segments={artifacts.corrected_segments_path}")
    print(f"report={artifacts.report_path}")
    print(f"manifest={artifacts.manifest_path}")
    return 0
```

- [ ] **Step 6: Run targeted tests**

Run:

```bash
uv run pytest -q tests/test_cli.py::test_parse_correct_asr_with_ocr_command tests/test_orchestration.py::test_effective_task_a_segments_prefers_corrected_segments tests/test_orchestration.py::test_effective_task_a_segments_falls_back_to_original
```

Expected: PASS.

---

### Task 3: Insert the Workflow Node with Low-Coupling Dependencies

**Files:**
- Modify: `src/translip/types.py`
- Modify: `src/translip/orchestration/nodes.py`
- Modify: `src/translip/orchestration/templates.py`
- Modify: `src/translip/orchestration/graph.py`
- Modify: `src/translip/orchestration/graph_export.py`
- Modify: `src/translip/orchestration/runner.py`
- Modify: `tests/test_workflow_graph.py`
- Modify: `tests/test_orchestration.py`

- [ ] **Step 1: Add failing workflow graph tests**

In `tests/test_workflow_graph.py`, update the OCR template expectation:

```python
def test_resolve_template_plan_for_asr_dub_ocr_subs() -> None:
    plan = resolve_template_plan("asr-dub+ocr-subs")

    assert plan.template_id == "asr-dub+ocr-subs"
    assert plan.node_order == [
        "stage1",
        "ocr-detect",
        "task-a",
        "asr-ocr-correct",
        "task-b",
        "task-c",
        "ocr-translate",
        "task-d",
        "task-e",
        "task-g",
    ]
    assert plan.nodes["asr-ocr-correct"].required is True
    assert plan.dependencies_for("task-b") == ("asr-ocr-correct",)
```

Add:

```python
def test_basic_template_does_not_include_asr_ocr_correction() -> None:
    plan = resolve_template_plan("asr-dub-basic")

    assert "asr-ocr-correct" not in plan.nodes
    assert plan.dependencies_for("task-b") == ("stage1", "task-a")
```

- [ ] **Step 2: Add failing runner command test**

In `tests/test_orchestration.py`, add:

```python
def test_run_pipeline_executes_asr_ocr_correction_before_task_b(tmp_path: Path, monkeypatch) -> None:
    from translip.orchestration.runner import run_pipeline
    from translip.types import PipelineRequest

    input_path = tmp_path / "sample.mp4"
    input_path.write_text("placeholder", encoding="utf-8")
    request = PipelineRequest(
        input_path=input_path,
        output_root=tmp_path / "workflow-out",
        template_id="asr-dub+ocr-subs",
        run_to_stage="task-b",
    )

    calls: list[str] = []

    def fake_execute(node_name: str, *_args, **_kwargs):
        calls.append(node_name)
        node_dir = request.output_root / node_name / "voice"
        node_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = node_dir / f"{node_name}.json"
        manifest_path.write_text(json.dumps({"status": "succeeded"}), encoding="utf-8")
        return {"manifest_path": str(manifest_path), "artifact_paths": [str(manifest_path)]}

    monkeypatch.setattr("translip.orchestration.runner.execute_node", fake_execute)

    run_pipeline(request)

    assert calls == ["stage1", "ocr-detect", "task-a", "asr-ocr-correct", "task-b"]
```

- [ ] **Step 3: Run tests to verify they fail**

Run:

```bash
uv run pytest -q tests/test_workflow_graph.py tests/test_orchestration.py::test_run_pipeline_executes_asr_ocr_correction_before_task_b
```

Expected: FAIL because `asr-ocr-correct` is not registered and resolved plans do not expose `dependencies_for`.

- [ ] **Step 4: Add node type and registry entry**

In `src/translip/types.py`, add `"asr-ocr-correct"` to both `WorkflowNodeName` and `PipelineStageName`.

In `src/translip/orchestration/nodes.py`, add:

```python
"asr-ocr-correct": WorkflowNodeDef(
    "asr-ocr-correct",
    "audio-spine",
    ("task-a", "ocr-detect"),
    35,
),
```

Keep global `task-b` dependencies as `("stage1", "task-a")`; OCR-template-specific dependency is handled in templates.

- [ ] **Step 5: Add template-specific dependencies**

In `src/translip/orchestration/templates.py`, extend `TemplateDef`:

```python
dependency_overrides: dict[WorkflowNodeName, tuple[WorkflowNodeName, ...]] = field(default_factory=dict)
```

For OCR templates, include `asr-ocr-correct` and add:

```python
dependency_overrides={"task-b": ("asr-ocr-correct",)}
```

For `asr-dub+ocr-subs`, set:

```python
selected_nodes=("stage1", "task-a", "asr-ocr-correct", "task-b", "task-c", "task-d", "task-e", "ocr-detect", "ocr-translate", "task-g")
required_nodes=("stage1", "task-a", "asr-ocr-correct", "task-b", "task-c", "task-d", "task-e", "ocr-detect", "ocr-translate", "task-g")
```

For `asr-dub+ocr-subs+erase`, include `asr-ocr-correct` in selected and required nodes.

- [ ] **Step 6: Resolve dependencies from the template plan**

In `src/translip/orchestration/graph.py`, add dependencies to `ResolvedTemplatePlan`:

```python
dependencies: dict[WorkflowNodeName, tuple[WorkflowNodeName, ...]]

def dependencies_for(self, node_name: WorkflowNodeName) -> tuple[WorkflowNodeName, ...]:
    return self.dependencies.get(node_name, ())
```

Build `dependencies` by using `template.dependency_overrides[node]` when present, otherwise `NODE_REGISTRY[node].dependencies`. Use this resolved dependency map in `_collect_nodes` and `_topological_order`.

- [ ] **Step 7: Use plan dependencies when exporting graph edges**

In `src/translip/orchestration/graph_export.py`, replace:

```python
for dependency in NODE_REGISTRY[node_name].dependencies
```

with:

```python
for dependency in plan.dependencies_for(node_name)
```

- [ ] **Step 8: Add runner support and cache artifacts**

In `src/translip/orchestration/runner.py`, import:

```python
build_asr_ocr_correction_command,
effective_task_a_segments_path,
task_a_corrected_segments_path,
task_a_corrected_srt_path,
task_a_correction_manifest_path,
task_a_correction_report_path,
```

In `_stage_cache_payload`, add:

```python
elif stage_name == "asr-ocr-correct":
    common.update({"transcription_correction": dict(request.transcription_correction)})
```

In `_node_cache_spec`, add:

```python
elif stage_name == "asr-ocr-correct":
    manifest_path = task_a_correction_manifest_path(request)
    artifact_paths = [
        task_a_corrected_segments_path(request),
        task_a_corrected_srt_path(request),
        task_a_correction_report_path(request),
        manifest_path,
    ]
```

In `_final_artifacts`, change:

```python
"segments_path": str(task_a_segments_path(request)),
```

to:

```python
"segments_path": str(effective_task_a_segments_path(request)),
```

In `execute_node`, add before `task-g`:

```python
if node_name == "asr-ocr-correct":
    monitor.update_stage_progress(node_name, 5.0, "correcting ASR transcript with OCR")
    run_stage_command(build_asr_ocr_correction_command(request), log_path=_node_log_path(request, node_name))
    return {
        "manifest_path": str(task_a_correction_manifest_path(request)),
        "artifact_paths": [
            str(task_a_corrected_segments_path(request)),
            str(task_a_corrected_srt_path(request)),
            str(task_a_correction_report_path(request)),
            str(task_a_correction_manifest_path(request)),
        ],
        "log_path": str(_node_log_path(request, node_name)),
    }
```

- [ ] **Step 9: Add legacy stage ordering support**

In `src/translip/orchestration/stages.py`, insert `asr-ocr-correct` after `task-a`:

```python
STAGE_ORDER: list[PipelineStageName] = [
    "stage1",
    "task-a",
    "asr-ocr-correct",
    "task-b",
    "task-c",
    "task-d",
    "task-e",
    "task-g",
]
```

Add a small weight:

```python
"asr-ocr-correct": 0.05,
```

- [ ] **Step 10: Run workflow tests**

Run:

```bash
uv run pytest -q tests/test_workflow_graph.py tests/test_orchestration.py::test_run_pipeline_executes_asr_ocr_correction_before_task_b
```

Expected: PASS.

---

### Task 4: Add Backend Config Defaults and Read-Model Summary

**Files:**
- Modify: `src/translip/server/task_config.py`
- Modify: `src/translip/server/schemas.py`
- Modify: `src/translip/server/task_manager.py`
- Modify: `src/translip/server/task_read_model.py`
- Modify: `tests/test_task_config_normalization.py`
- Modify: `tests/test_task_read_models.py`

- [ ] **Step 1: Add failing config and read-model tests**

In `tests/test_task_config_normalization.py`, add:

```python
def test_transcription_correction_defaults_to_standard_for_pipeline_config() -> None:
    from translip.server.task_config import normalize_task_config

    config = normalize_task_config({"template": "asr-dub+ocr-subs"})

    assert config["transcription_correction"] == {
        "enabled": True,
        "preset": "standard",
        "ocr_only_policy": "report_only",
        "llm_arbitration": "off",
    }
```

Add:

```python
def test_build_pipeline_request_maps_transcription_correction(tmp_path: Path) -> None:
    from translip.server.task_manager import _build_pipeline_request

    task = Task(
        id="task-correction-config",
        name="Correction Config",
        status="pending",
        input_path=str(tmp_path / "input.mp4"),
        output_root=str(tmp_path / "output"),
        source_lang="zh",
        target_lang="en",
        config={
            "pipeline": {
                "template": "asr-dub+ocr-subs",
                "transcription_correction": {
                    "enabled": False,
                    "preset": "conservative",
                    "ocr_only_policy": "report_only",
                    "llm_arbitration": "off",
                },
            }
        },
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )

    request = _build_pipeline_request(task)

    assert request.transcription_correction["enabled"] is False
    assert request.transcription_correction["preset"] == "conservative"
```

In `tests/test_task_read_models.py`, add:

```python
def test_task_read_model_surfaces_transcription_correction_summary(tmp_path: Path) -> None:
    from translip.server.task_read_model import build_task_read

    output_root = tmp_path / "task-output"
    report_path = output_root / "asr-ocr-correct" / "voice" / "correction-report.json"
    report_path.parent.mkdir(parents=True)
    report_path.write_text(
        json.dumps(
            {
                "summary": {
                    "segment_count": 10,
                    "corrected_count": 6,
                    "kept_asr_count": 3,
                    "review_count": 1,
                    "ocr_only_count": 1,
                    "auto_correction_rate": 0.6,
                    "review_rate": 0.1,
                    "fallback_reason": None,
                    "algorithm_version": "ocr-guided-asr-correction-v1",
                }
            }
        ),
        encoding="utf-8",
    )
    task = Task(
        id="task-correction-summary",
        name="Correction Summary",
        status="succeeded",
        input_path=str(tmp_path / "input.mp4"),
        output_root=str(output_root),
        source_lang="zh",
        target_lang="en",
        config={"pipeline": {"template": "asr-dub+ocr-subs"}},
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )

    payload = build_task_read(task, stages=[])

    assert payload["transcription_correction_summary"]["corrected_count"] == 6
    assert payload["transcription_correction_summary"]["ocr_only_count"] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest -q tests/test_task_config_normalization.py tests/test_task_read_models.py::test_task_read_model_surfaces_transcription_correction_summary
```

Expected: FAIL because defaults and summary field do not exist.

- [ ] **Step 3: Add config defaults and schema fields**

In `src/translip/server/task_config.py`, add:

```python
_TRANSCRIPTION_CORRECTION_DEFAULTS = {
    "enabled": True,
    "preset": "standard",
    "ocr_only_policy": "report_only",
    "llm_arbitration": "off",
}
```

In `normalize_task_storage`, after building `pipeline`, normalize:

```python
pipeline["transcription_correction"] = {
    **_TRANSCRIPTION_CORRECTION_DEFAULTS,
    **dict(pipeline.get("transcription_correction") or {}),
}
```

In `src/translip/server/schemas.py`, add:

```python
transcription_correction: Dict[str, Any] = {
    "enabled": True,
    "preset": "standard",
    "ocr_only_policy": "report_only",
    "llm_arbitration": "off",
}
```

to `TaskConfigInput`, and add:

```python
transcription_correction_summary: Dict[str, Any] = {}
```

to `TaskRead`.

- [ ] **Step 4: Map config into `PipelineRequest`**

In `src/translip/server/task_manager.py`, pass:

```python
transcription_correction=cfg.get(
    "transcription_correction",
    {
        "enabled": True,
        "preset": "standard",
        "ocr_only_policy": "report_only",
        "llm_arbitration": "off",
    },
),
```

to `PipelineRequest`.

- [ ] **Step 5: Surface correction summary**

In `src/translip/server/task_read_model.py`, add:

```python
def build_transcription_correction_summary(task: Task) -> dict[str, Any]:
    report_path = Path(task.output_root) / "asr-ocr-correct" / "voice" / "correction-report.json"
    if not report_path.exists():
        return {
            "status": "not_available",
            "corrected_count": 0,
            "kept_asr_count": 0,
            "review_count": 0,
            "ocr_only_count": 0,
        }
    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except Exception:
        return {"status": "unreadable", "corrected_count": 0, "kept_asr_count": 0, "review_count": 0, "ocr_only_count": 0}
    summary = dict(payload.get("summary") or {})
    return {"status": "available", **summary}
```

Add this to the task read payload:

```python
"transcription_correction_summary": build_transcription_correction_summary(task),
```

- [ ] **Step 6: Run backend config/read-model tests**

Run:

```bash
uv run pytest -q tests/test_task_config_normalization.py tests/test_task_read_models.py::test_task_read_model_surfaces_transcription_correction_summary
```

Expected: PASS.

---

### Task 5: Add the Transcript Correction Atomic Tool

**Files:**
- Modify: `src/translip/server/atomic_tools/schemas.py`
- Create: `src/translip/server/atomic_tools/adapters/transcript_correction.py`
- Modify: `src/translip/server/atomic_tools/adapters/__init__.py`
- Modify: `tests/test_atomic_tools_registry.py`
- Add: `tests/test_atomic_tools_adapters/test_transcript_correction_adapter.py`

- [ ] **Step 1: Add failing registry and adapter tests**

Update `tests/test_atomic_tools_registry.py` so the registry expects the new tool:

```python
from __future__ import annotations


def test_atomic_tools_registry_exposes_all_eight_tools() -> None:
    import translip.server.atomic_tools as atomic_tools  # noqa: F401
    from translip.server.atomic_tools.registry import get_all_tools

    tools = get_all_tools()

    assert [tool.tool_id for tool in tools] == [
        "separation",
        "mixing",
        "transcription",
        "transcript-correction",
        "translation",
        "tts",
        "probe",
        "muxing",
    ]
    assert {tool.category for tool in tools} == {"audio", "speech", "video"}
    correction = next(tool for tool in tools if tool.tool_id == "transcript-correction")
    assert correction.name_zh == "台词校正"
    assert correction.category == "speech"
    assert correction.max_files == 2
    assert ".json" in correction.accept_formats
    assert next(tool for tool in tools if tool.tool_id == "probe").max_file_size_mb == 2000
```

Add `tests/test_atomic_tools_adapters/test_transcript_correction_adapter.py`:

```python
from __future__ import annotations

import json
from pathlib import Path


def test_transcript_correction_adapter_writes_artifacts_and_summary(tmp_path: Path) -> None:
    from translip.server.atomic_tools.adapters.transcript_correction import TranscriptCorrectionAdapter

    input_dir = tmp_path / "input"
    segments_file = input_dir / "segments_file" / "segments.zh.json"
    ocr_file = input_dir / "ocr_events_file" / "ocr_events.json"
    segments_file.parent.mkdir(parents=True)
    ocr_file.parent.mkdir(parents=True)
    segments_file.write_text(
        json.dumps(
            {
                "segments": [
                    {
                        "id": "seg-0001",
                        "start": 0.0,
                        "end": 2.0,
                        "duration": 2.0,
                        "speaker_label": "SPEAKER_00",
                        "text": "虽扛下了天洁",
                        "language": "zh",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    ocr_file.write_text(
        json.dumps(
            {
                "events": [
                    {
                        "event_id": "evt-0001",
                        "start": 0.1,
                        "end": 1.8,
                        "text": "虽扛下了天劫",
                        "confidence": 0.99,
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    output_dir = tmp_path / "output"
    progress: list[tuple[float, str | None]] = []

    result = TranscriptCorrectionAdapter().run(
        {
            "segments_file_id": "segments-file-id",
            "ocr_events_file_id": "ocr-events-file-id",
            "enabled": True,
            "preset": "standard",
            "ocr_only_policy": "report_only",
        },
        input_dir,
        output_dir,
        lambda pct, step=None: progress.append((pct, step)),
    )

    assert (output_dir / "segments.zh.corrected.json").exists()
    assert (output_dir / "segments.zh.corrected.srt").exists()
    assert (output_dir / "correction-report.json").exists()
    assert (output_dir / "correction-manifest.json").exists()
    corrected = json.loads((output_dir / "segments.zh.corrected.json").read_text(encoding="utf-8"))
    assert corrected["segments"][0]["text"] == "虽扛下了天劫"
    assert result["segment_count"] == 1
    assert result["corrected_count"] == 1
    assert result["ocr_only_count"] == 0
    assert result["algorithm_version"] == "ocr-guided-asr-correction-v1"
    assert result["corrected_segments_file"] == "segments.zh.corrected.json"
    assert progress[0] == (5.0, "loading_inputs")
```

Add request validation coverage in the same file:

```python
def test_transcript_correction_adapter_validates_default_params() -> None:
    from translip.server.atomic_tools.adapters.transcript_correction import TranscriptCorrectionAdapter

    params = TranscriptCorrectionAdapter().validate_params(
        {
            "segments_file_id": "segments-file-id",
            "ocr_events_file_id": "ocr-events-file-id",
        }
    )

    assert params["enabled"] is True
    assert params["preset"] == "standard"
    assert params["ocr_only_policy"] == "report_only"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest -q tests/test_atomic_tools_registry.py tests/test_atomic_tools_adapters/test_transcript_correction_adapter.py
```

Expected: FAIL because `transcript-correction` is not registered and the adapter module does not exist.

- [ ] **Step 3: Add the atomic request schema**

In `src/translip/server/atomic_tools/schemas.py`, add:

```python
class TranscriptCorrectionToolRequest(BaseModel):
    segments_file_id: str
    ocr_events_file_id: str
    enabled: bool = True
    preset: Literal["conservative", "standard", "aggressive"] = "standard"
    ocr_only_policy: Literal["report_only"] = "report_only"
```

Do not add OCR fields to `TranscriptionToolRequest`; the existing transcription atomic tool stays raw ASR.

- [ ] **Step 4: Implement the adapter and register the tool**

Create `src/translip/server/atomic_tools/adapters/transcript_correction.py`:

```python
from __future__ import annotations

from ....transcription.ocr_correction import (
    CorrectionConfig,
    correct_asr_segments_with_ocr,
    load_json_payload,
    write_correction_artifacts,
)
from ..registry import ToolSpec, register_tool
from ..schemas import TranscriptCorrectionToolRequest
from . import ToolAdapter


def _config_from_params(params: dict) -> CorrectionConfig:
    preset = params.get("preset", "standard")
    factories = {
        "conservative": CorrectionConfig.conservative,
        "standard": CorrectionConfig.standard,
        "aggressive": CorrectionConfig.aggressive,
    }
    config = factories[preset]()
    if params.get("enabled", True) is False:
        return CorrectionConfig(enabled=False, preset=preset)
    return config


class TranscriptCorrectionAdapter(ToolAdapter):
    def validate_params(self, params: dict) -> dict:
        return TranscriptCorrectionToolRequest(**params).model_dump()

    def run(self, params, input_dir, output_dir, on_progress):
        segments_file = self.first_input(input_dir, "segments_file")
        ocr_events_file = self.first_input(input_dir, "ocr_events_file")
        on_progress(5.0, "loading_inputs")
        segments_payload = load_json_payload(segments_file)
        ocr_payload = load_json_payload(ocr_events_file)
        config = _config_from_params(params)

        on_progress(35.0, "correcting_transcript")
        result = correct_asr_segments_with_ocr(
            segments_payload=segments_payload,
            ocr_payload=ocr_payload,
            config=config,
        )

        on_progress(80.0, "writing_artifacts")
        artifacts = write_correction_artifacts(result, output_dir=output_dir)
        summary = dict(result.report.get("summary") or {})

        on_progress(95.0, "finalizing")
        return {
            "status": "succeeded",
            "segment_count": summary.get("segment_count", 0),
            "corrected_count": summary.get("corrected_count", 0),
            "kept_asr_count": summary.get("kept_asr_count", 0),
            "review_count": summary.get("review_count", 0),
            "ocr_only_count": summary.get("ocr_only_count", 0),
            "algorithm_version": summary.get("algorithm_version", config.algorithm_version),
            "corrected_segments_file": artifacts.corrected_segments_path.name,
            "corrected_srt_file": artifacts.corrected_srt_path.name,
            "report_file": artifacts.report_path.name,
            "manifest_file": artifacts.manifest_path.name,
        }


register_tool(
    ToolSpec(
        tool_id="transcript-correction",
        name_zh="台词校正",
        name_en="Transcript Correction",
        description_zh="使用 OCR 字幕校正 ASR 文稿，保留 ASR 时间轴和说话人",
        description_en="Correct ASR transcript text with OCR subtitle events while preserving ASR timing and speakers",
        category="speech",
        icon="ScanText",
        accept_formats=[".json"],
        max_file_size_mb=500,
        max_files=2,
    ),
    TranscriptCorrectionAdapter,
)
```

In `src/translip/server/atomic_tools/adapters/__init__.py`, import the adapter immediately after transcription so registry order is stable:

```python
from .transcription import TranscriptionAdapter  # noqa: E402,F401
from .transcript_correction import TranscriptCorrectionAdapter  # noqa: E402,F401
```

- [ ] **Step 5: Run atomic tool tests**

Run:

```bash
uv run pytest -q tests/test_atomic_tools_registry.py tests/test_atomic_tools_adapters/test_transcript_correction_adapter.py tests/test_atomic_tools_adapters/test_transcription_adapter.py
```

Expected: PASS, including the existing transcription adapter test.

---

### Task 6: Add Frontend Defaults, Explanation, and Summary

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/pages/NewTaskPage.tsx`
- Modify: `frontend/src/pages/TaskDetailPage.tsx`
- Modify: `frontend/src/lib/workflowPreview.ts`
- Modify: `frontend/src/i18n/formatters.ts`
- Modify: `frontend/src/i18n/messages.ts`
- Modify: `frontend/src/pages/__tests__/NewTaskPage.test.tsx`
- Modify: `frontend/src/pages/__tests__/TaskDetailPage.delivery.test.tsx`

- [ ] **Step 1: Add failing frontend tests**

In `frontend/src/pages/__tests__/NewTaskPage.test.tsx`, add a test that selects the bilingual review intent and verifies correction defaults:

```tsx
it('defaults OCR-capable tasks to standard transcript correction and explains the setting', async () => {
  render(<NewTaskPage />)

  await userEvent.click(screen.getByRole('button', { name: /双语审片版/ }))
  await userEvent.click(screen.getByRole('button', { name: /下一步/ }))
  await userEvent.click(screen.getByRole('button', { name: /下一步/ }))

  expect(screen.getByText('台词校正')).toBeInTheDocument()
  expect(screen.getByText('标准')).toBeInTheDocument()

  await userEvent.click(screen.getByRole('button', { name: /这个选项会做什么/ }))
  expect(screen.getByText(/保留 ASR 时间轴和说话人/)).toBeInTheDocument()
  expect(screen.getByText(/OCR 有但 ASR 没有的字幕只报告/)).toBeInTheDocument()
})
```

In `frontend/src/pages/__tests__/TaskDetailPage.delivery.test.tsx`, add:

```tsx
it('shows transcript correction summary when available', async () => {
  mockTaskDetail({
    transcription_correction_summary: {
      status: 'available',
      corrected_count: 18,
      kept_asr_count: 5,
      review_count: 2,
      ocr_only_count: 1,
      auto_correction_rate: 0.692,
      algorithm_version: 'ocr-guided-asr-correction-v1',
    },
  })

  render(<TaskDetailPage />)

  expect(await screen.findByText('台词校正')).toBeInTheDocument()
  expect(screen.getByText('已校正 18 段')).toBeInTheDocument()
  expect(screen.getByText('2 段建议复核')).toBeInTheDocument()
  expect(screen.getByText('OCR 漏配 1 条')).toBeInTheDocument()
})
```

- [ ] **Step 2: Run frontend tests to verify they fail**

Run:

```bash
cd frontend && npm test -- --run src/pages/__tests__/NewTaskPage.test.tsx src/pages/__tests__/TaskDetailPage.delivery.test.tsx
```

Expected: FAIL because types and UI do not exist.

- [ ] **Step 3: Add frontend types**

In `frontend/src/types/index.ts`, add:

```ts
export type TranscriptionCorrectionPreset = 'conservative' | 'standard' | 'aggressive'

export interface TranscriptionCorrectionConfig {
  enabled: boolean
  preset: TranscriptionCorrectionPreset
  ocr_only_policy: 'report_only'
  llm_arbitration: 'off'
}

export interface TranscriptionCorrectionSummary {
  status: 'not_available' | 'available' | 'unreadable'
  corrected_count: number
  kept_asr_count: number
  review_count: number
  ocr_only_count: number
  auto_correction_rate?: number
  review_rate?: number
  algorithm_version?: string
}
```

Add to `TaskConfig`:

```ts
transcription_correction?: Partial<TranscriptionCorrectionConfig>
```

Add to `Task`:

```ts
transcription_correction_summary?: TranscriptionCorrectionSummary
```

- [ ] **Step 4: Update `NewTaskPage` defaults and UI**

In `defaultConfig`, add:

```ts
transcription_correction: {
  enabled: true,
  preset: 'standard',
  ocr_only_policy: 'report_only',
  llm_arbitration: 'off',
},
```

Add helpers:

```ts
function supportsTranscriptCorrection(template: TaskConfig['template'] | undefined) {
  return template === 'asr-dub+ocr-subs' || template === 'asr-dub+ocr-subs+erase'
}

function patchTranscriptionCorrection(config: Partial<TaskConfig>, patch: Partial<TranscriptionCorrectionConfig>): Partial<TaskConfig> {
  return {
    ...config,
    transcription_correction: {
      enabled: true,
      preset: 'standard',
      ocr_only_policy: 'report_only',
      llm_arbitration: 'off',
      ...(config.transcription_correction ?? {}),
      ...patch,
    },
  }
}
```

In the “更多设置” section, show for OCR templates:

```tsx
<Field
  label={locale === 'zh-CN' ? '台词校正' : 'Transcript Correction'}
  hint={locale === 'zh-CN'
    ? '默认使用标准强度：保留 ASR 时间轴，只替换高置信 OCR 台词文本。'
    : 'Standard by default: keep ASR timing and replace only high-confidence OCR dialogue.'}
>
  <Checkbox
    checked={config.transcription_correction?.enabled ?? true}
    onChange={value => setConfig(prev => patchTranscriptionCorrection(prev, { enabled: value }))}
    label={locale === 'zh-CN' ? '使用画面字幕校正 ASR 文稿' : 'Use screen subtitles to correct ASR text'}
  />
  <Select
    value={config.transcription_correction?.preset ?? 'standard'}
    onChange={value => setConfig(prev => patchTranscriptionCorrection(prev, { preset: value as TranscriptionCorrectionPreset }))}
    options={[
      { value: 'conservative', label: locale === 'zh-CN' ? '保守' : 'Conservative' },
      { value: 'standard', label: locale === 'zh-CN' ? '标准' : 'Standard' },
      { value: 'aggressive', label: locale === 'zh-CN' ? '积极' : 'Aggressive' },
    ]}
  />
</Field>
```

Add a small collapsed button labelled `这个选项会做什么` that reveals the design explanation text from the spec.

- [ ] **Step 5: Update task detail summary**

In `TaskDetailPage.tsx`, render a compact summary if `task.transcription_correction_summary?.status === 'available'`:

```tsx
<section className="rounded-lg border border-slate-200 bg-white p-4">
  <div className="text-sm font-semibold text-slate-900">台词校正</div>
  <div className="mt-2 flex flex-wrap gap-2 text-xs text-slate-600">
    <span>已校正 {summary.corrected_count} 段</span>
    <span>{summary.review_count} 段建议复核</span>
    <span>OCR 漏配 {summary.ocr_only_count} 条</span>
  </div>
</section>
```

- [ ] **Step 6: Update frontend workflow preview**

In `frontend/src/lib/workflowPreview.ts`, add node:

```ts
'asr-ocr-correct': { group: 'audio-spine', dependencies: ['task-a', 'ocr-detect'], column: 3 },
```

Update OCR templates:

```ts
const TEMPLATE_DEFINITIONS: Record<
  TemplateId,
  { nodeIds: readonly string[]; requiredIds: readonly string[]; dependencyOverrides?: Record<string, readonly string[]> }
> = {
  'asr-dub-basic': {
    nodeIds: ['stage1', 'task-a', 'task-b', 'task-c', 'task-d', 'task-e', 'task-g'],
    requiredIds: ['stage1', 'task-a', 'task-b', 'task-c', 'task-d', 'task-e', 'task-g'],
  },
  'asr-dub+ocr-subs': {
    nodeIds: ['stage1', 'ocr-detect', 'task-a', 'asr-ocr-correct', 'task-b', 'task-c', 'ocr-translate', 'task-d', 'task-e', 'task-g'],
    requiredIds: ['stage1', 'ocr-detect', 'task-a', 'asr-ocr-correct', 'task-b', 'task-c', 'ocr-translate', 'task-d', 'task-e', 'task-g'],
    dependencyOverrides: { 'task-b': ['asr-ocr-correct'] },
  },
  'asr-dub+ocr-subs+erase': {
    nodeIds: ['stage1', 'ocr-detect', 'task-a', 'asr-ocr-correct', 'task-b', 'task-c', 'ocr-translate', 'task-d', 'task-e', 'subtitle-erase', 'task-g'],
    requiredIds: ['stage1', 'ocr-detect', 'task-a', 'asr-ocr-correct', 'task-b', 'task-c', 'task-d', 'task-e', 'task-g'],
    dependencyOverrides: { 'task-b': ['asr-ocr-correct'] },
  },
}
```

Update `buildEdges` to honor template dependency overrides:

```ts
function buildEdges(nodes: WorkflowGraphNode[], dependencyOverrides: Record<string, readonly string[]> = {}) {
  const nodeSet = new Set(nodes.map(node => node.id))
  const statusByNode = new Map(nodes.map(node => [node.id, node.status]))
  const edges: WorkflowGraphEdge[] = []

  for (const node of nodes) {
    const definition = WORKFLOW_NODE_DEFINITIONS[node.id]
    const dependencies = dependencyOverrides[node.id] ?? definition?.dependencies ?? []
    for (const dependency of dependencies) {
      if (!nodeSet.has(dependency)) {
        continue
      }
      edges.push({
        from: dependency,
        to: node.id,
        state: edgeState(
          statusByNode.get(dependency) ?? 'pending',
          statusByNode.get(node.id) ?? 'pending',
        ),
      })
    }
  }

  return edges
}
```

Update calls:

```ts
edges: buildEdges(nodes, template.dependencyOverrides)
```

In `frontend/src/i18n/formatters.ts`, insert `asr-ocr-correct` after `task-a` in `STAGE_ORDER`.

In `frontend/src/i18n/messages.ts`, add Chinese and English labels:

```ts
'asr-ocr-correct': 'OCR 校正文稿'
```

```ts
'asr-ocr-correct': 'OCR Correction'
```

- [ ] **Step 7: Run frontend tests**

Run:

```bash
cd frontend && npm test -- --run src/pages/__tests__/NewTaskPage.test.tsx src/pages/__tests__/TaskDetailPage.delivery.test.tsx src/lib/__tests__/workflowPreview.test.ts
```

Expected: PASS.

---

### Task 7: Run Focused and Broad Verification

**Files:**
- No code changes expected unless verification reveals a bug.

- [ ] **Step 1: Run backend focused suites**

Run:

```bash
uv run pytest -q \
  tests/test_asr_ocr_correction.py \
  tests/test_cli.py \
  tests/test_workflow_graph.py \
  tests/test_orchestration.py \
  tests/test_task_config_normalization.py \
  tests/test_task_read_models.py \
  tests/test_atomic_tools_registry.py \
  tests/test_atomic_tools_adapters/test_transcript_correction_adapter.py \
  tests/test_atomic_tools_adapters/test_transcription_adapter.py
```

Expected: PASS.

- [ ] **Step 2: Run frontend focused suites**

Run:

```bash
cd frontend && npm test -- --run \
  src/pages/__tests__/NewTaskPage.test.tsx \
  src/pages/__tests__/TaskDetailPage.delivery.test.tsx \
  src/lib/__tests__/workflowPreview.test.ts
```

Expected: PASS.

- [ ] **Step 3: Run full backend tests if focused suites pass**

Run:

```bash
uv run pytest -q
```

Expected: PASS.

- [ ] **Step 4: Run full frontend tests if focused suites pass**

Run:

```bash
cd frontend && npm test -- --run
```

Expected: PASS.

- [ ] **Step 5: Validate against `task-20260420-014221` artifacts**

Run the new CLI against existing artifacts:

```bash
uv run translip correct-asr-with-ocr \
  --segments /Users/masamiyui/.cache/translip/output-pipeline/task-20260420-014221/task-a/voice/segments.zh.json \
  --ocr-events /Users/masamiyui/.cache/translip/output-pipeline/task-20260420-014221/ocr-detect/ocr_events.json \
  --output-dir /tmp/translip-ocr-correction-check \
  --preset standard
```

Expected:

- `/tmp/translip-ocr-correction-check/voice/segments.zh.corrected.json` exists
- `/tmp/translip-ocr-correction-check/voice/correction-report.json` exists
- Corrected text includes `虽扛下了天劫`
- Corrected text includes `讨伐龙族`
- Corrected text includes `小爷是魔`
- Report includes OCR-only `那又如何`
- Corrected segment count remains equal to original ASR segment count

## Self-Review Checklist

- Spec coverage:
  - Default standard correction: Task 4, Task 5, and Task 6.
  - OCR-only report-only behavior: Task 1.
  - Effective segment path centralization: Task 2 and Task 3.
  - Algorithm version and quality metrics: Task 1 and Task 4.
  - Low-coupling workflow dependency: Task 3.
  - Atomic `transcript-correction` tool without changing raw `transcription`: Task 5.
  - UI hidden explanation: Task 6.
  - Glossary ordering: Task 2 and Task 3 route Task C through corrected Chinese before existing glossary logic.
- No global suitability precheck is added.
- No automatic OCR-only insertion is added.
- No full-script LLM correction is added.
