from __future__ import annotations

import json
from pathlib import Path

import pytest

from translip.vision.config import load_settings
from translip.vision.services.vision_service import (
    MAX_CONSECUTIVE_FAILURES,
    AnalyzeRequest,
    analyze_video,
)


class FakeBackend:
    backend_name = "fake"
    model_id = "fake-model"

    def __init__(self, responses=None, *, error_after: int | None = None) -> None:
        self.responses = responses or []
        self.error_after = error_after
        self.calls: list[tuple[list[Path], str]] = []
        self.loaded = False
        self.closed = False

    def load(self) -> None:
        self.loaded = True

    def chat(self, images: list[Path], prompt: str) -> str:
        if self.error_after is not None and len(self.calls) >= self.error_after:
            raise RuntimeError("backend down")
        self.calls.append((images, prompt))
        if self.responses:
            return self.responses[min(len(self.calls) - 1, len(self.responses) - 1)]
        return '{"scene": "ok", "people_visible": 1, "confidence": 0.9}'

    def close(self) -> None:
        self.closed = True


def _write_video_stub(tmp_path: Path) -> Path:
    video = tmp_path / "input.mp4"
    video.write_bytes(b"\x00")
    return video


def _patch_frames(monkeypatch, tmp_path: Path) -> None:
    def fake_extract_batch(video_path, timestamps, output_paths, *, max_edge=768):
        for path in output_paths:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"jpg")
        return list(output_paths)

    monkeypatch.setattr(
        "translip.vision.services.vision_service.extract_frames_batch", fake_extract_batch
    )
    # Identical stub bytes would make every frame "similar"; disable scene-skip
    # by default so existing call-count assertions stay meaningful.
    monkeypatch.setenv("VISION_SCENE_SKIP_THRESHOLD", "0")
    monkeypatch.setattr(
        "translip.vision.services.vision_service.video_duration_sec", lambda _p: 30.0
    )


def test_env_overrides_apply_without_reimport(monkeypatch) -> None:
    monkeypatch.setenv("VISION_BACKEND", "ollama")
    monkeypatch.setenv("VISION_FRAMES_PER_UNIT", "99")  # clamped to 8
    monkeypatch.setenv("VISION_OLLAMA_MODEL", "qwen3-vl:8b-instruct")
    settings = load_settings()
    assert settings.backend == "ollama"
    assert settings.frames_per_unit == 8
    assert settings.ollama_model == "qwen3-vl:8b-instruct"


def test_scene_context_with_segments_writes_units_and_manifest(tmp_path, monkeypatch) -> None:
    _patch_frames(monkeypatch, tmp_path)
    video = _write_video_stub(tmp_path)
    segments = tmp_path / "segments.json"
    segments.write_text(
        json.dumps(
            {
                "segments": [
                    {"id": "seg-0001", "start": 0.0, "end": 3.0},
                    {"id": "seg-0002", "start": 10.0, "end": 13.0},
                ]
            }
        ),
        encoding="utf-8",
    )
    backend = FakeBackend()
    progress: list[tuple[float, str]] = []

    result = analyze_video(
        AnalyzeRequest(
            input_path=video,
            output_dir=tmp_path / "out",
            task="scene-context",
            segments_path=segments,
        ),
        backend_override=backend,
        progress_callback=lambda pct, msg: progress.append((pct, msg)),
    )

    assert backend.loaded and backend.closed
    assert result.manifest["status"] == "succeeded"
    assert result.unit_count == 2 and result.error_count == 0
    payload = json.loads(result.artifact_path.read_text(encoding="utf-8"))
    assert payload["task"] == "scene-context"
    assert payload["model"] == {"backend": "fake", "model": "fake-model"}
    first = payload["units"][0]
    assert first["unit_id"] == "vis-0001"
    assert first["segment_ids"] == ["seg-0001"]
    assert first["scene"] == "ok"
    assert "frames_sampled" in first
    assert result.manifest_path.name == "scene-context-manifest.json"
    assert progress[0][1] == "planning_units" and progress[-1][1] == "completed"


def test_scene_context_without_segments_uses_interval_units(tmp_path, monkeypatch) -> None:
    _patch_frames(monkeypatch, tmp_path)
    video = _write_video_stub(tmp_path)
    backend = FakeBackend()
    result = analyze_video(
        AnalyzeRequest(
            input_path=video,
            output_dir=tmp_path / "out",
            task="scene-context",
            sample_interval_sec=10.0,
        ),
        backend_override=backend,
    )
    # 30s duration / 10s interval = 3 units, bare-video mode has no segment ids
    assert result.unit_count == 3
    payload = json.loads(result.artifact_path.read_text(encoding="utf-8"))
    assert all(unit["segment_ids"] == [] for unit in payload["units"])


def test_max_units_subsamples_evenly(tmp_path, monkeypatch) -> None:
    _patch_frames(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "translip.vision.services.vision_service.video_duration_sec", lambda _p: 100.0
    )
    video = _write_video_stub(tmp_path)
    backend = FakeBackend()
    result = analyze_video(
        AnalyzeRequest(
            input_path=video,
            output_dir=tmp_path / "out",
            task="scene-context",
            sample_interval_sec=10.0,
            max_units=4,
        ),
        backend_override=backend,
    )
    assert result.unit_count == 4
    assert result.manifest["dropped_unit_count"] == 6


def test_parse_error_degrades_unit_not_run(tmp_path, monkeypatch) -> None:
    _patch_frames(monkeypatch, tmp_path)
    video = _write_video_stub(tmp_path)
    backend = FakeBackend(responses=["not json at all", '{"scene": "fine"}'])
    result = analyze_video(
        AnalyzeRequest(
            input_path=video,
            output_dir=tmp_path / "out",
            task="scene-context",
            sample_interval_sec=15.0,
        ),
        backend_override=backend,
    )
    assert result.manifest["status"] == "succeeded"
    assert result.error_count == 1
    payload = json.loads(result.artifact_path.read_text(encoding="utf-8"))
    assert "error" in payload["units"][0]
    assert payload["units"][1]["scene"] == "fine"


def test_consecutive_backend_failures_fail_fast(tmp_path, monkeypatch) -> None:
    _patch_frames(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "translip.vision.services.vision_service.video_duration_sec", lambda _p: 200.0
    )
    video = _write_video_stub(tmp_path)
    backend = FakeBackend(error_after=0)  # every call raises
    result = analyze_video(
        AnalyzeRequest(
            input_path=video,
            output_dir=tmp_path / "out",
            task="scene-context",
            sample_interval_sec=10.0,
        ),
        backend_override=backend,
    )
    assert result.manifest["status"] == "failed"
    assert "consecutive" in result.manifest["error"]
    assert result.unit_count == MAX_CONSECUTIVE_FAILURES
    assert backend.closed


def test_ocr_classify_annotates_original_events(tmp_path, monkeypatch) -> None:
    _patch_frames(monkeypatch, tmp_path)
    video = _write_video_stub(tmp_path)
    detection = tmp_path / "ocr_events.json"
    detection.write_text(
        json.dumps(
            {
                "video": {"fps": 25},
                "events": [
                    {"event_id": "evt-0001", "start": 1.0, "end": 2.0, "text": "你好"},
                    {"event_id": "evt-0002", "start": 3.0, "end": 4.0, "text": "芒果tv"},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    backend = FakeBackend(
        responses=['{"kind": "subtitle", "confidence": 0.95}', '{"kind": "watermark", "confidence": 0.9}']
    )
    result = analyze_video(
        AnalyzeRequest(
            input_path=video,
            output_dir=tmp_path / "out",
            task="ocr-classify",
            detection_path=detection,
        ),
        backend_override=backend,
    )
    payload = json.loads(result.artifact_path.read_text(encoding="utf-8"))
    # Original envelope preserved, events annotated in place.
    assert payload["video"] == {"fps": 25}
    assert payload["events"][0]["kind"] == "subtitle"
    assert payload["events"][1]["kind"] == "watermark"
    assert payload["events"][0]["text"] == "你好"
    assert result.artifact_path.name == "ocr_events.classified.json"
    # Per-event prompt embeds the OCR text.
    assert "你好" in backend.calls[0][1]
    assert "芒果tv" in backend.calls[1][1]
    # One midpoint frame per event regardless of frames_per_unit default.
    assert len(backend.calls[0][0]) == 1


def test_erase_qc_summary_counts_flagged(tmp_path, monkeypatch) -> None:
    _patch_frames(monkeypatch, tmp_path)
    video = _write_video_stub(tmp_path)
    detection = tmp_path / "detection.json"
    detection.write_text(
        json.dumps(
            {
                "events": [
                    {"event_id": "evt-0001", "start": 1.0, "end": 2.0},
                    {"event_id": "evt-0002", "start": 3.0, "end": 4.0},
                ]
            }
        ),
        encoding="utf-8",
    )
    backend = FakeBackend(
        responses=[
            '{"residual_text": true, "artifact": "blur_patch", "note": "leftover", "confidence": 0.8}',
            '{"residual_text": false, "artifact": null, "note": "clean", "confidence": 0.9}',
        ]
    )
    result = analyze_video(
        AnalyzeRequest(
            input_path=video,
            output_dir=tmp_path / "out",
            task="erase-qc",
            detection_path=detection,
        ),
        backend_override=backend,
    )
    payload = json.loads(result.artifact_path.read_text(encoding="utf-8"))
    assert payload["summary"] == {"checked": 2, "flagged": 1, "pass_rate": 0.5}


def test_freeform_requires_question_and_answers(tmp_path, monkeypatch) -> None:
    _patch_frames(monkeypatch, tmp_path)
    video = _write_video_stub(tmp_path)
    with pytest.raises(ValueError, match="question"):
        analyze_video(
            AnalyzeRequest(input_path=video, output_dir=tmp_path / "out", task="freeform"),
            backend_override=FakeBackend(),
        )

    backend = FakeBackend(responses=['{"answer": "两次", "confidence": 0.7}'])
    result = analyze_video(
        AnalyzeRequest(
            input_path=video,
            output_dir=tmp_path / "out2",
            task="freeform",
            question="出现几次手机？",
        ),
        backend_override=backend,
    )
    payload = json.loads(result.artifact_path.read_text(encoding="utf-8"))
    assert payload["answer"] == "两次"
    assert payload["question"] == "出现几次手机？"
    assert "出现几次手机？" in backend.calls[0][1]


def test_ocr_classify_without_detection_rejected(tmp_path) -> None:
    video = _write_video_stub(tmp_path)
    with pytest.raises(ValueError, match="detection"):
        analyze_video(
            AnalyzeRequest(input_path=video, output_dir=tmp_path / "out", task="ocr-classify"),
            backend_override=FakeBackend(),
        )


def test_missing_input_rejected(tmp_path) -> None:
    with pytest.raises(FileNotFoundError):
        analyze_video(
            AnalyzeRequest(input_path=tmp_path / "nope.mp4", output_dir=tmp_path / "out"),
            backend_override=FakeBackend(),
        )


def test_scene_skip_reuses_previous_result_for_similar_frames(tmp_path, monkeypatch) -> None:
    _patch_frames(monkeypatch, tmp_path)
    monkeypatch.setenv("VISION_SCENE_SKIP_THRESHOLD", "4.0")
    # All stub frames identical -> signature distance 0 -> every unit after the
    # first reuses its payload without calling the backend.
    monkeypatch.setattr(
        "translip.vision.services.vision_service.frame_signature",
        lambda _path, grid=16: [128] * (16 * 16),
    )
    video = _write_video_stub(tmp_path)
    backend = FakeBackend(responses=['{"scene": "同一场景", "people_visible": 2, "confidence": 0.9}'])
    result = analyze_video(
        AnalyzeRequest(
            input_path=video,
            output_dir=tmp_path / "out",
            task="scene-context",
            sample_interval_sec=10.0,  # 30s duration -> 3 units
        ),
        backend_override=backend,
    )
    assert len(backend.calls) == 1  # only the first unit hit the model
    assert result.manifest["skipped_similar_count"] == 2
    payload = json.loads(result.artifact_path.read_text(encoding="utf-8"))
    assert all(unit["scene"] == "同一场景" for unit in payload["units"])
    assert payload["units"][1]["reused_previous"] is True
    # Reused rows keep their own time spans.
    assert payload["units"][1]["start"] == 10.0


def test_scene_skip_disabled_for_other_tasks(tmp_path, monkeypatch) -> None:
    _patch_frames(monkeypatch, tmp_path)
    monkeypatch.setenv("VISION_SCENE_SKIP_THRESHOLD", "4.0")
    monkeypatch.setattr(
        "translip.vision.services.vision_service.frame_signature",
        lambda _path, grid=16: [128] * (16 * 16),
    )
    video = _write_video_stub(tmp_path)
    detection = tmp_path / "d.json"
    detection.write_text(
        json.dumps(
            {
                "events": [
                    {"event_id": "evt-0001", "start": 1.0, "end": 2.0, "text": "a"},
                    {"event_id": "evt-0002", "start": 3.0, "end": 4.0, "text": "b"},
                ]
            }
        ),
        encoding="utf-8",
    )
    backend = FakeBackend(responses=['{"kind": "subtitle", "confidence": 0.9}'])
    result = analyze_video(
        AnalyzeRequest(
            input_path=video, output_dir=tmp_path / "out", task="ocr-classify", detection_path=detection
        ),
        backend_override=backend,
    )
    assert len(backend.calls) == 2  # classification never skips
    assert result.manifest["skipped_similar_count"] == 0


def test_scene_skip_tolerates_missing_pillow(tmp_path, monkeypatch) -> None:
    _patch_frames(monkeypatch, tmp_path)
    monkeypatch.setenv("VISION_SCENE_SKIP_THRESHOLD", "4.0")
    # frame_signature returns None when Pillow is unavailable -> no skipping,
    # but also no crash.
    monkeypatch.setattr(
        "translip.vision.services.vision_service.frame_signature", lambda _path, grid=16: None
    )
    video = _write_video_stub(tmp_path)
    backend = FakeBackend()
    result = analyze_video(
        AnalyzeRequest(
            input_path=video, output_dir=tmp_path / "out", task="scene-context", sample_interval_sec=10.0
        ),
        backend_override=backend,
    )
    assert len(backend.calls) == 3
    assert result.manifest["skipped_similar_count"] == 0
