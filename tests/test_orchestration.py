from __future__ import annotations

import json
import sys
from pathlib import Path

from translip.orchestration.request import build_pipeline_request
from translip.orchestration.stages import resolve_stage_sequence
from translip.translation.backend import BackendSegmentOutput


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


def test_build_pipeline_request_keeps_template_and_delivery_policy() -> None:
    request = build_pipeline_request(
        {
            "input": "sample.mp4",
            "output_root": "out",
            "template": "asr-dub+ocr-subs",
            "subtitle_source": "both",
            "video_source": "clean_if_available",
            "audio_source": "both",
        }
    )

    assert request.template_id == "asr-dub+ocr-subs"
    assert request.delivery_policy["subtitle_source"] == "both"
    assert request.delivery_policy["video_source"] == "clean_if_available"


def test_build_pipeline_request_keeps_external_project_roots() -> None:
    request = build_pipeline_request(
        {
            "input": "sample.mp4",
            "output_root": "out",
            "ocr_project_root": "/tmp/subtitle-ocr",
            "erase_project_root": "/tmp/video-subtitle-erasure",
        }
    )

    assert Path(request.ocr_project_root) == Path("/tmp/subtitle-ocr").resolve()
    assert Path(request.erase_project_root) == Path("/tmp/video-subtitle-erasure").resolve()


def test_build_pipeline_request_defaults_to_moss_tts_nano_onnx() -> None:
    request = build_pipeline_request(
        {
            "input": "sample.mp4",
            "output_root": "out",
        }
    )

    assert request.tts_backend == "moss-tts-nano-onnx"
    assert request.tts_backends == ["moss-tts-nano-onnx"]


def test_build_pipeline_request_accepts_candidate_tts_backends() -> None:
    request = build_pipeline_request(
        {
            "input": "sample.mp4",
            "output_root": "out",
            "tts_backend": "moss-tts-nano-onnx",
            "candidate_tts_backends": ["qwen3tts"],
        }
    )

    assert request.tts_backend == "moss-tts-nano-onnx"
    assert request.tts_backends == ["moss-tts-nano-onnx", "qwen3tts"]


def test_build_pipeline_request_keeps_translation_batch_size() -> None:
    request = build_pipeline_request(
        {
            "input": "sample.mp4",
            "output_root": "out",
            "translation_batch_size": 2,
        }
    )

    assert request.translation_batch_size == 2


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


def test_effective_task_a_segments_prefers_speaker_corrected_segments(tmp_path: Path) -> None:
    from translip.orchestration.commands import (
        effective_task_a_segments_path,
        task_a_corrected_segments_path,
        task_a_speaker_corrected_segments_path,
        task_a_segments_path,
    )
    from translip.types import PipelineRequest

    request = PipelineRequest(input_path=tmp_path / "sample.mp4", output_root=tmp_path / "out")
    original = task_a_segments_path(request)
    corrected = task_a_corrected_segments_path(request)
    speaker_corrected = task_a_speaker_corrected_segments_path(request)
    original.parent.mkdir(parents=True)
    original.write_text("{}", encoding="utf-8")
    corrected.parent.mkdir(parents=True)
    corrected.write_text("{}", encoding="utf-8")
    speaker_corrected.write_text("{}", encoding="utf-8")

    assert effective_task_a_segments_path(request) == speaker_corrected


def test_effective_task_a_segments_prefers_text_corrected_before_original(tmp_path: Path) -> None:
    from translip.orchestration.commands import (
        effective_task_a_segments_path,
        task_a_corrected_segments_path,
        task_a_segments_path,
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


def test_run_pipeline_executes_nodes_from_template_plan(tmp_path: Path, monkeypatch) -> None:
    from translip.orchestration.runner import run_pipeline
    from translip.types import PipelineRequest

    input_path = tmp_path / "sample.mp4"
    input_path.write_text("placeholder", encoding="utf-8")
    request = PipelineRequest(
        input_path=input_path,
        output_root=tmp_path / "workflow-out",
        template_id="asr-dub-basic",
    )

    monkeypatch.setattr(
        "translip.orchestration.runner.resolve_template_plan",
        lambda template_id: type(
            "Plan",
            (),
            {
                "template_id": template_id,
                "node_order": ["stage1", "task-a", "task-b"],
                "nodes": {
                    "stage1": type("Node", (), {"required": True})(),
                    "task-a": type("Node", (), {"required": True})(),
                    "task-b": type("Node", (), {"required": True})(),
                },
            },
        )(),
    )

    calls: list[str] = []

    def fake_execute(node_name: str, *_args, **_kwargs):
        calls.append(node_name)
        node_dir = request.output_root / node_name
        node_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = node_dir / f"{node_name}.json"
        manifest_path.write_text(json.dumps({"status": "succeeded"}), encoding="utf-8")
        return {"manifest_path": str(manifest_path), "artifact_paths": [str(manifest_path)]}

    monkeypatch.setattr("translip.orchestration.runner.execute_node", fake_execute)

    result = run_pipeline(request)

    assert calls == ["stage1", "task-a", "task-b"]
    payload = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert payload["status"] == "succeeded"


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


def test_run_pipeline_marks_partial_success_when_optional_node_fails(tmp_path: Path, monkeypatch) -> None:
    from translip.orchestration.runner import run_pipeline
    from translip.types import PipelineRequest

    input_path = tmp_path / "sample.mp4"
    input_path.write_text("placeholder", encoding="utf-8")
    request = PipelineRequest(
        input_path=input_path,
        output_root=tmp_path / "workflow-out",
        template_id="asr-dub+ocr-subs+erase",
        run_to_stage="task-g",
    )

    monkeypatch.setattr(
        "translip.orchestration.runner.resolve_template_plan",
        lambda _template_id: type(
            "Plan",
            (),
            {
                "template_id": "asr-dub+ocr-subs+erase",
                "node_order": ["stage1", "ocr-detect", "subtitle-erase", "task-g"],
                "nodes": {
                    "stage1": type("Node", (), {"required": True})(),
                    "ocr-detect": type("Node", (), {"required": True})(),
                    "subtitle-erase": type("Node", (), {"required": False})(),
                    "task-g": type("Node", (), {"required": True})(),
                },
            },
        )(),
    )

    def fake_execute(node_name: str, *_args, **_kwargs):
        if node_name == "subtitle-erase":
            raise RuntimeError("erase failed")
        node_dir = request.output_root / node_name
        node_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = node_dir / f"{node_name}.json"
        manifest_path.write_text(json.dumps({"status": "succeeded"}), encoding="utf-8")
        return {"manifest_path": str(manifest_path), "artifact_paths": [str(manifest_path)]}

    monkeypatch.setattr("translip.orchestration.runner.execute_node", fake_execute)

    result = run_pipeline(request)

    payload = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert payload["status"] == "partial_success"


def test_translate_ocr_events_writes_json_and_srt(tmp_path: Path) -> None:
    from translip.subtitles.runner import translate_ocr_events

    class FakeBackend:
        backend_name = "fake"
        resolved_model = "fake-model"
        resolved_device = "cpu"

        def translate_batch(self, *, items, source_lang: str, target_lang: str):
            return [
                BackendSegmentOutput(segment_id=item.segment_id, target_text=f"{target_lang}:{item.source_text}")
                for item in items
            ]

    events_path = tmp_path / "ocr_events.json"
    events_path.write_text(
        json.dumps(
            {
                "events": [
                    {
                        "event_id": "evt-1",
                        "start": 0.0,
                        "end": 1.5,
                        "text": "你好",
                        "language": "zh",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = translate_ocr_events(
        events_path=events_path,
        output_dir=tmp_path / "ocr-translate",
        target_lang="en",
        backend_name="local-m2m100",
        backend_override=FakeBackend(),
    )

    assert result.json_path.exists()
    assert result.srt_path.exists()
    payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert payload["events"][0]["translated_text"] == "en:你好"


def test_translate_ocr_events_uses_batches_and_reports_progress(tmp_path: Path) -> None:
    from translip.subtitles.runner import translate_ocr_events

    class FakeBackend:
        backend_name = "fake"
        resolved_model = "fake-model"
        resolved_device = "cpu"

        def __init__(self) -> None:
            self.batch_sizes: list[int] = []

        def translate_batch(self, *, items, source_lang: str, target_lang: str):
            self.batch_sizes.append(len(items))
            return [
                BackendSegmentOutput(segment_id=item.segment_id, target_text=f"{target_lang}:{item.source_text}")
                for item in items
            ]

    events = [
        {
            "event_id": f"evt-{index}",
            "start": float(index),
            "end": float(index) + 1.0,
            "text": f"字幕{index}",
            "language": "zh",
        }
        for index in range(5)
    ]
    events_path = tmp_path / "ocr_events.json"
    events_path.write_text(json.dumps({"events": events}), encoding="utf-8")
    backend = FakeBackend()
    progress: list[tuple[int, int]] = []

    result = translate_ocr_events(
        events_path=events_path,
        output_dir=tmp_path / "ocr-translate",
        target_lang="en",
        backend_name="local-m2m100",
        backend_override=backend,
        batch_size=2,
        progress_callback=lambda completed, total: progress.append((completed, total)),
    )

    assert backend.batch_sizes == [2, 2, 1]
    assert progress == [(2, 5), (4, 5), (5, 5)]
    payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert [event["translated_text"] for event in payload["events"]] == [
        "en:字幕0",
        "en:字幕1",
        "en:字幕2",
        "en:字幕3",
        "en:字幕4",
    ]
