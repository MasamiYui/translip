from __future__ import annotations

import json
import sys
from pathlib import Path

from translip.orchestration.request import build_pipeline_request
from translip.orchestration.stages import resolve_stage_sequence


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


def test_pipeline_status_snapshot_contains_overall_and_stage_progress(tmp_path: Path) -> None:
    from translip.orchestration.monitor import PipelineMonitor

    status_path = tmp_path / "pipeline-status.json"
    monitor = PipelineMonitor(job_id="job-1", status_path=status_path, write_status=True)
    monitor.start_stage("task-d", current_step="speaker spk_0001 0/10")
    monitor.update_stage_progress("task-d", 25.0, "speaker spk_0001 2/10")
    payload = json.loads(status_path.read_text(encoding="utf-8"))
    assert payload["status"] == "running"
    assert payload["current_stage"] == "task-d"
    assert payload["overall_progress_percent"] > 0
    assert payload["stages"][0]["progress_percent"] == 25.0


def test_stage_cache_hits_when_manifest_and_artifacts_exist(tmp_path: Path) -> None:
    from translip.orchestration.cache import StageCacheSpec, is_stage_cache_hit

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


def test_stage1_command_uses_python_module_cli(tmp_path: Path) -> None:
    from translip.orchestration.commands import build_stage1_command
    from translip.types import PipelineRequest

    request = PipelineRequest(input_path=tmp_path / "sample.mp4", output_root=tmp_path / "out")
    command = build_stage1_command(request)
    assert command[:3] == [sys.executable, "-m", "translip"]
    assert command[3] == "run"


def test_run_pipeline_writes_manifest_report_and_status(tmp_path: Path, monkeypatch) -> None:
    from translip.orchestration.runner import run_pipeline
    from translip.types import PipelineRequest

    request = PipelineRequest(
        input_path=tmp_path / "sample.mp4",
        output_root=tmp_path / "pipeline-out",
        run_to_stage="task-c",
        write_status=True,
    )
    request.input_path.write_text("placeholder", encoding="utf-8")

    calls: list[str] = []

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


def test_pipeline_runner_marks_cached_stage_when_manifest_reusable(tmp_path: Path, monkeypatch) -> None:
    from translip.orchestration.runner import run_pipeline
    from translip.types import PipelineRequest

    input_path = tmp_path / "sample.mp4"
    input_path.write_text("placeholder", encoding="utf-8")
    output_root = tmp_path / "pipeline-out"
    manifest_path = output_root / "task-a" / "voice" / "task-a-manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps({"status": "succeeded"}), encoding="utf-8")
    artifact_path = output_root / "task-a" / "voice" / "segments.zh.json"
    artifact_path.write_text("{}", encoding="utf-8")
    request = PipelineRequest(
        input_path=input_path,
        output_root=output_root,
        run_from_stage="task-a",
        run_to_stage="task-a",
    )

    executed: list[str] = []

    def fake_stage_executor(stage_name: str, *_args, **_kwargs):
        executed.append(stage_name)
        return {"manifest_path": str(manifest_path), "artifact_paths": [str(artifact_path)]}

    monkeypatch.setattr("translip.orchestration.runner.execute_stage", fake_stage_executor)

    result = run_pipeline(request)

    assert executed == []
    payload = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert payload["stages"][0]["status"] == "cached"
