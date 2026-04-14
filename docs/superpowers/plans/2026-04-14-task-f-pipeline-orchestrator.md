# Task F Pipeline Orchestrator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a resumable Stage 1 → Task E pipeline orchestrator with cache-aware stage reuse, status snapshots, and a unified CLI entry point.

**Architecture:** Keep existing stage CLIs and manifests intact. Add a thin orchestration layer that validates requests, resolves stage order, runs stage commands in subprocesses, records stage status to `pipeline-status.json`, and emits `pipeline-manifest.json` plus `pipeline-report.json`.

**Tech Stack:** Python 3.11, argparse, dataclasses, subprocess, JSON manifests, pytest

---

### Task 1: Add Task F CLI Surface

**Files:**
- Modify: `src/translip/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write the failing parser test**

```python
def test_cli_run_pipeline_parser() -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "run-pipeline",
            "--input",
            "sample.mp4",
            "--output-root",
            "pipeline-output",
            "--target-lang",
            "en",
            "--resume",
            "--write-status",
        ]
    )
    assert args.command == "run-pipeline"
    assert args.input == "sample.mp4"
    assert args.output_root == "pipeline-output"
    assert args.target_lang == "en"
    assert args.resume is True
    assert args.write_status is True
```

- [ ] **Step 2: Run the parser test to verify it fails**

Run: `uv run pytest -q tests/test_cli.py::test_cli_run_pipeline_parser`

Expected: FAIL because `run-pipeline` does not exist yet.

- [ ] **Step 3: Add the minimal parser wiring**

Add a `run-pipeline` subcommand with the first-wave Task F arguments:

```python
pipeline_parser = subparsers.add_parser(
    "run-pipeline",
    help="Run stage 1 through task-e with cache-aware orchestration",
)
pipeline_parser.add_argument("--config", default=None)
pipeline_parser.add_argument("--input", required=True)
pipeline_parser.add_argument("--output-root", default="output-pipeline")
pipeline_parser.add_argument("--target-lang", default=DEFAULT_TRANSLATION_TARGET_LANG)
pipeline_parser.add_argument(
    "--translation-backend",
    default=DEFAULT_TRANSLATION_BACKEND,
    choices=["local-m2m100", "siliconflow"],
)
pipeline_parser.add_argument(
    "--tts-backend",
    default=DEFAULT_DUBBING_BACKEND,
    choices=["qwen3tts"],
)
pipeline_parser.add_argument("--device", default=DEFAULT_DEVICE, choices=["auto", "cpu", "cuda", "mps"])
pipeline_parser.add_argument("--run-from-stage", default="stage1")
pipeline_parser.add_argument("--run-to-stage", default="task-e")
pipeline_parser.add_argument("--resume", action="store_true")
pipeline_parser.add_argument("--force-stage", action="append", dest="force_stages")
pipeline_parser.add_argument("--reuse-existing", dest="reuse_existing", action="store_true", default=True)
pipeline_parser.add_argument("--no-reuse-existing", dest="reuse_existing", action="store_false")
pipeline_parser.add_argument("--write-status", dest="write_status", action="store_true", default=True)
pipeline_parser.add_argument("--no-write-status", dest="write_status", action="store_false")
pipeline_parser.add_argument("--status-update-interval-sec", type=float, default=2.0)
```

- [ ] **Step 4: Run the parser test to verify it passes**

Run: `uv run pytest -q tests/test_cli.py::test_cli_run_pipeline_parser`

Expected: PASS

### Task 2: Add Pipeline Request, Stage Order, and Config Merge

**Files:**
- Modify: `src/translip/types.py`
- Create: `src/translip/orchestration/__init__.py`
- Create: `src/translip/orchestration/request.py`
- Create: `src/translip/orchestration/stages.py`
- Test: `tests/test_orchestration.py`

- [ ] **Step 1: Write failing request and stage tests**

```python
def test_pipeline_request_merges_json_config_with_cli_override(tmp_path: Path) -> None:
    config_path = tmp_path / "pipeline.json"
    config_path.write_text(
        json.dumps(
            {
                "target_lang": "ja",
                "translation_backend": "local-m2m100",
                "write_status": False,
            }
        ),
        encoding="utf-8",
    )
    request = build_pipeline_request(
        {
            "config": str(config_path),
            "input": "sample.mp4",
            "output_root": "out",
            "target_lang": "en",
            "translation_backend": None,
            "write_status": True,
        }
    )
    assert request.target_lang == "en"
    assert request.translation_backend == "local-m2m100"
    assert request.write_status is True


def test_stage_sequence_respects_from_and_to() -> None:
    stages = resolve_stage_sequence("task-b", "task-d")
    assert stages == ["task-b", "task-c", "task-d"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest -q tests/test_orchestration.py::test_pipeline_request_merges_json_config_with_cli_override tests/test_orchestration.py::test_stage_sequence_respects_from_and_to`

Expected: FAIL because the request builder and stage resolver do not exist.

- [ ] **Step 3: Add minimal request and stage modules**

Add a pipeline request dataclass with normalized paths and config merge:

```python
PipelineStageName = Literal["stage1", "task-a", "task-b", "task-c", "task-d", "task-e"]
```

Add a resolver:

```python
STAGE_ORDER = ["stage1", "task-a", "task-b", "task-c", "task-d", "task-e"]

def resolve_stage_sequence(run_from_stage: str, run_to_stage: str) -> list[str]:
    start = STAGE_ORDER.index(run_from_stage)
    end = STAGE_ORDER.index(run_to_stage)
    if start > end:
        raise ValueError("run_from_stage must be before or equal to run_to_stage")
    return STAGE_ORDER[start : end + 1]
```

- [ ] **Step 4: Run the new tests to verify they pass**

Run: `uv run pytest -q tests/test_orchestration.py::test_pipeline_request_merges_json_config_with_cli_override tests/test_orchestration.py::test_stage_sequence_respects_from_and_to`

Expected: PASS

### Task 3: Add Pipeline Status Snapshot and Report Builders

**Files:**
- Create: `src/translip/orchestration/export.py`
- Create: `src/translip/orchestration/monitor.py`
- Test: `tests/test_orchestration.py`

- [ ] **Step 1: Write failing status/report tests**

```python
def test_pipeline_status_snapshot_contains_overall_and_stage_progress(tmp_path: Path) -> None:
    status_path = tmp_path / "pipeline-status.json"
    monitor = PipelineMonitor(status_path=status_path, write_status=True)
    monitor.start_stage("task-d", current_step="speaker spk_0001 0/10")
    monitor.update_stage_progress("task-d", 25.0, "speaker spk_0001 2/10")
    payload = json.loads(status_path.read_text(encoding="utf-8"))
    assert payload["status"] == "running"
    assert payload["current_stage"] == "task-d"
    assert payload["overall_progress_percent"] > 0
    assert payload["stages"][0]["progress_percent"] == 25.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/test_orchestration.py::test_pipeline_status_snapshot_contains_overall_and_stage_progress`

Expected: FAIL because the monitor does not exist.

- [ ] **Step 3: Implement the minimal monitor and export helpers**

Add a monitor that writes:

```python
{
  "job_id": "...",
  "status": "running",
  "overall_progress_percent": 25.0,
  "current_stage": "task-d",
  "updated_at": "...",
  "stages": [...]
}
```

Use fixed weights:

```python
STAGE_WEIGHTS = {
    "stage1": 0.10,
    "task-a": 0.10,
    "task-b": 0.10,
    "task-c": 0.15,
    "task-d": 0.35,
    "task-e": 0.20,
}
```

- [ ] **Step 4: Run the status test to verify it passes**

Run: `uv run pytest -q tests/test_orchestration.py::test_pipeline_status_snapshot_contains_overall_and_stage_progress`

Expected: PASS

### Task 4: Add Cache Validation and Stage Summaries

**Files:**
- Create: `src/translip/orchestration/cache.py`
- Test: `tests/test_orchestration.py`

- [ ] **Step 1: Write the failing cache test**

```python
def test_stage_cache_hits_when_manifest_and_artifacts_exist(tmp_path: Path) -> None:
    manifest_path = tmp_path / "task-a-manifest.json"
    artifact_path = tmp_path / "segments.zh.json"
    manifest_path.write_text(json.dumps({"status": "succeeded"}), encoding="utf-8")
    artifact_path.write_text("{}", encoding="utf-8")
    stage = StageCacheSpec(
        stage_name="task-a",
        manifest_path=manifest_path,
        artifact_paths=[artifact_path],
        cache_key="abc",
        previous_cache_key="abc",
    )
    assert is_stage_cache_hit(stage) is True
```

- [ ] **Step 2: Run the cache test to verify it fails**

Run: `uv run pytest -q tests/test_orchestration.py::test_stage_cache_hits_when_manifest_and_artifacts_exist`

Expected: FAIL because cache helpers do not exist.

- [ ] **Step 3: Implement minimal cache helpers**

Implement:

```python
def is_stage_cache_hit(spec: StageCacheSpec) -> bool:
    if not spec.manifest_path.exists():
        return False
    if not all(path.exists() for path in spec.artifact_paths):
        return False
    payload = json.loads(spec.manifest_path.read_text(encoding="utf-8"))
    return payload.get("status") == "succeeded" and spec.cache_key == spec.previous_cache_key
```

- [ ] **Step 4: Run the cache test to verify it passes**

Run: `uv run pytest -q tests/test_orchestration.py::test_stage_cache_hits_when_manifest_and_artifacts_exist`

Expected: PASS

### Task 5: Implement Subprocess Runner and Stage Command Builder

**Files:**
- Create: `src/translip/orchestration/subprocess_runner.py`
- Create: `src/translip/orchestration/commands.py`
- Test: `tests/test_orchestration.py`

- [ ] **Step 1: Write failing stage command tests**

```python
def test_stage1_command_uses_translip_cli(tmp_path: Path) -> None:
    request = PipelineRequest(input_path=tmp_path / "sample.mp4", output_root=tmp_path / "out")
    command = build_stage1_command(request)
    assert command[:3] == [sys.executable, "-m", "translip"]
    assert command[3] == "run"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/test_orchestration.py::test_stage1_command_uses_translip_cli`

Expected: FAIL because command builders do not exist.

- [ ] **Step 3: Implement minimal stage command builders**

Build subprocess commands using `sys.executable -m translip` for:

- `stage1`
- `task-a`
- `task-b`
- `task-c`
- `task-d`
- `task-e`

Do not shell out through `translip` path lookup.

- [ ] **Step 4: Run the stage command test to verify it passes**

Run: `uv run pytest -q tests/test_orchestration.py::test_stage1_command_uses_translip_cli`

Expected: PASS

### Task 6: Implement Pipeline Runner End-to-End in Process with Fake Subprocesses

**Files:**
- Create: `src/translip/orchestration/runner.py`
- Modify: `src/translip/cli.py`
- Test: `tests/test_orchestration.py`

- [ ] **Step 1: Write the failing pipeline runner test**

```python
def test_run_pipeline_writes_manifest_report_and_status(tmp_path: Path, monkeypatch) -> None:
    request = PipelineRequest(
        input_path=tmp_path / "sample.mp4",
        output_root=tmp_path / "pipeline-out",
        run_to_stage="task-c",
        write_status=True,
    )
    request.input_path.write_text("placeholder", encoding="utf-8")

    calls = []

    def fake_stage_executor(stage_name: str, *_args, **_kwargs):
        calls.append(stage_name)
        stage_dir = request.output_root / stage_name
        stage_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = stage_dir / f"{stage_name}.json"
        manifest_path.write_text(json.dumps({"status": "succeeded"}), encoding="utf-8")
        return {"manifest_path": str(manifest_path), "artifact_paths": [str(manifest_path)]}

    monkeypatch.setattr("translip.orchestration.runner.execute_stage", fake_stage_executor)

    result = run_pipeline(request)

    assert calls == ["stage1", "task-a", "task-b", "task-c"]
    assert result.manifest_path.exists()
    assert result.report_path.exists()
    assert result.status_path.exists()
```

- [ ] **Step 2: Run the pipeline runner test to verify it fails**

Run: `uv run pytest -q tests/test_orchestration.py::test_run_pipeline_writes_manifest_report_and_status`

Expected: FAIL because the runner does not exist.

- [ ] **Step 3: Implement the minimal runner**

Implement:

- request normalization
- stage sequence resolution
- per-stage status transitions
- monitor updates
- final manifest and report writes

Use dependency injection for the subprocess executor so tests can fake it.

- [ ] **Step 4: Run the pipeline runner test to verify it passes**

Run: `uv run pytest -q tests/test_orchestration.py::test_run_pipeline_writes_manifest_report_and_status`

Expected: PASS

### Task 7: Wire Real Stage Execution for Stage 1 Through Task E

**Files:**
- Modify: `src/translip/orchestration/runner.py`
- Modify: `src/translip/orchestration/commands.py`
- Modify: `src/translip/orchestration/subprocess_runner.py`
- Test: `tests/test_orchestration.py`

- [ ] **Step 1: Write the failing resume/cache behavior test**

```python
def test_pipeline_runner_marks_cached_stage_when_manifest_reusable(tmp_path: Path, monkeypatch) -> None:
    input_path = tmp_path / "sample.mp4"
    input_path.write_text("placeholder", encoding="utf-8")
    output_root = tmp_path / "pipeline-out"
    manifest_path = output_root / "task-a" / "voice" / "task-a-manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps({"status": "succeeded"}), encoding="utf-8")
    artifact_path = output_root / "task-a" / "voice" / "segments.zh.json"
    artifact_path.write_text("{}", encoding="utf-8")
    request = PipelineRequest(input_path=input_path, output_root=output_root, run_from_stage="task-a", run_to_stage="task-a")

    executed = []
    monkeypatch.setattr("translip.orchestration.runner.execute_stage", lambda *args, **kwargs: executed.append(args[0]))

    result = run_pipeline(request)

    assert executed == []
    payload = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert payload["stages"][0]["status"] == "cached"
```

- [ ] **Step 2: Run the resume/cache test to verify it fails**

Run: `uv run pytest -q tests/test_orchestration.py::test_pipeline_runner_marks_cached_stage_when_manifest_reusable`

Expected: FAIL because cache integration is not wired into the runner yet.

- [ ] **Step 3: Integrate cache checks and real stage manifests**

Add per-stage artifact resolvers for:

- `stage1`: `<output_root>/stage1/<stem>/voice.mp3`, `background.mp3`, `manifest.json`
- `task-a`: `<output_root>/task-a/voice/segments.zh.json`, `task-a-manifest.json`
- `task-b`: `<output_root>/task-b/voice/speaker_profiles.json`, `task-b-manifest.json`
- `task-c`: `<output_root>/task-c/voice/translation.<lang>.json`, `task-c-manifest.json`
- `task-d`: `<output_root>/task-d/task-d-stage-manifest.json`
- `task-e`: `<output_root>/task-e/voice/task-e-manifest.json`

Make the runner skip execution when the cache resolver says the stage is reusable.

- [ ] **Step 4: Run the cache test to verify it passes**

Run: `uv run pytest -q tests/test_orchestration.py::test_pipeline_runner_marks_cached_stage_when_manifest_reusable`

Expected: PASS

### Task 8: Run the Full Test Suite and Real Pipeline Validation

**Files:**
- Modify as needed based on failures
- Verify: `tests/test_cli.py`
- Verify: `tests/test_orchestration.py`
- Verify: full suite

- [ ] **Step 1: Run focused orchestration tests**

Run: `uv run pytest -q tests/test_cli.py tests/test_orchestration.py`

Expected: PASS

- [ ] **Step 2: Run the full unit test suite**

Run: `uv run pytest -q`

Expected: PASS

- [ ] **Step 3: Run the full real pipeline on test_video**

Run:

```bash
uv run translip run-pipeline \
  --input ./test_video/我在迪拜等你.mp4 \
  --output-root ./tmp/pipeline-task-f \
  --target-lang en \
  --translation-backend local-m2m100 \
  --tts-backend qwen3tts \
  --run-to-stage task-e \
  --write-status \
  --resume
```

Expected:

- pipeline completes successfully
- writes `pipeline-manifest.json`
- writes `pipeline-report.json`
- writes `pipeline-status.json`
- produces Task E outputs under `tmp/pipeline-task-f/task-e/voice`

- [ ] **Step 4: If failures appear, fix them and rerun tests**

Run:

```bash
uv run pytest -q
uv run translip run-pipeline \
  --input ./test_video/我在迪拜等你.mp4 \
  --output-root ./tmp/pipeline-task-f \
  --target-lang en \
  --translation-backend local-m2m100 \
  --tts-backend qwen3tts \
  --run-to-stage task-e \
  --write-status \
  --resume
```

Expected: PASS until the real pipeline stabilizes.
