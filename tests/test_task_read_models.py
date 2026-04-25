from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from translip.server.app import app
from translip.server.database import get_session
from translip.server.models import Task


def _override_session(engine):
    def override():
        with Session(engine) as session:
            yield session

    return override


def test_task_read_exposes_intent_asset_summary_and_export_readiness(tmp_path: Path) -> None:
    db_path = tmp_path / "task-read-model.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)

    output_root = tmp_path / "output"
    (output_root / "task-e" / "voice").mkdir(parents=True)
    (output_root / "subtitle-erase").mkdir(parents=True)
    (output_root / "ocr-detect").mkdir(parents=True)
    (output_root / "ocr-translate").mkdir(parents=True)
    (output_root / "task-c" / "voice").mkdir(parents=True)

    (tmp_path / "input.mp4").write_bytes(b"video")
    (output_root / "task-e" / "voice" / "preview_mix.en.wav").write_bytes(b"preview")
    (output_root / "task-e" / "voice" / "dub_voice.en.wav").write_bytes(b"dub")
    (output_root / "subtitle-erase" / "clean_video.mp4").write_bytes(b"clean")
    (output_root / "ocr-detect" / "ocr_subtitles.source.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\n哪吒\n", encoding="utf-8")
    (output_root / "ocr-translate" / "ocr_subtitles.en.srt").write_text("1", encoding="utf-8")
    (output_root / "task-c" / "voice" / "translation.en.srt").write_text("1", encoding="utf-8")

    with Session(engine) as session:
        session.add(
            Task(
                id="task-ready",
                name="Task Ready",
                status="succeeded",
                input_path=str(tmp_path / "input.mp4"),
                output_root=str(output_root),
                source_lang="zh",
                target_lang="en",
                config={
                    "pipeline": {
                        "template": "asr-dub+ocr-subs+erase",
                        "run_to_stage": "task-g",
                        "video_source": "clean_if_available",
                        "audio_source": "both",
                        "subtitle_source": "both",
                        "output_intent": "english_subtitle",
                        "quality_preset": "high_quality",
                    },
                    "delivery": {
                        "subtitle_mode": "english_only",
                        "subtitle_render_source": "ocr",
                        "bilingual_export_strategy": "preserve_hard_subtitles_add_english",
                    },
                },
                created_at=datetime.now(),
                updated_at=datetime.now(),
            )
        )
        session.commit()

    app.dependency_overrides[get_session] = _override_session(engine)
    try:
        client = TestClient(app)
        response = client.get("/api/tasks/task-ready")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["output_intent"] == "english_subtitle"
    assert payload["quality_preset"] == "high_quality"
    assert payload["asset_summary"]["video"]["clean"]["status"] == "available"
    assert payload["asset_summary"]["audio"]["dub"]["status"] == "available"
    assert payload["asset_summary"]["subtitles"]["ocr_translated"]["status"] == "available"
    assert payload["hard_subtitle_status"] == "confirmed"
    assert payload["delivery_config"]["bilingual_export_strategy"] == "preserve_hard_subtitles_add_english"
    assert payload["export_readiness"]["status"] == "ready"
    assert payload["export_readiness"]["recommended_profile"] == "english_subtitle_burned"
    assert payload["export_readiness"]["blockers"] == []


def test_task_read_marks_english_subtitle_as_blocked_without_clean_video(tmp_path: Path) -> None:
    db_path = tmp_path / "task-read-blocked.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)

    output_root = tmp_path / "output"
    (output_root / "task-e" / "voice").mkdir(parents=True)
    (output_root / "ocr-translate").mkdir(parents=True)

    (tmp_path / "input.mp4").write_bytes(b"video")
    (output_root / "task-e" / "voice" / "dub_voice.en.wav").write_bytes(b"dub")
    (output_root / "ocr-translate" / "ocr_subtitles.en.srt").write_text("1", encoding="utf-8")

    with Session(engine) as session:
        session.add(
            Task(
                id="task-blocked",
                name="Task Blocked",
                status="succeeded",
                input_path=str(tmp_path / "input.mp4"),
                output_root=str(output_root),
                source_lang="zh",
                target_lang="en",
                config={
                    "pipeline": {
                        "template": "asr-dub+ocr-subs+erase",
                        "run_to_stage": "task-g",
                        "video_source": "clean_if_available",
                        "audio_source": "both",
                        "subtitle_source": "both",
                        "output_intent": "english_subtitle",
                    },
                    "delivery": {
                        "subtitle_mode": "english_only",
                        "subtitle_render_source": "ocr",
                    },
                },
                created_at=datetime.now(),
                updated_at=datetime.now(),
            )
        )
        session.commit()

    app.dependency_overrides[get_session] = _override_session(engine)
    try:
        client = TestClient(app)
        response = client.get("/api/tasks/task-blocked")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["asset_summary"]["video"]["clean"]["status"] == "missing"
    assert payload["export_readiness"]["status"] == "blocked"
    assert payload["export_readiness"]["recommended_profile"] == "english_subtitle_burned"
    assert payload["export_readiness"]["blockers"][0]["code"] == "missing_clean_video"
    assert payload["export_readiness"]["blockers"][0]["action"] == "rerun_subtitle_erase"


def test_task_read_exposes_last_export_summary(tmp_path: Path) -> None:
    db_path = tmp_path / "task-read-exported.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)

    output_root = tmp_path / "output"
    delivery_dir = output_root / "task-g" / "delivery"
    delivery_dir.mkdir(parents=True)
    exported = delivery_dir / "final_preview.en.mp4"
    exported.write_bytes(b"preview")
    stale_dub = output_root / "task-g" / "final-dub" / "final_dub.en.mp4"
    stale_dub.parent.mkdir(parents=True)
    stale_dub.write_bytes(b"stale dub")
    report_path = output_root / "task-g" / "delivery-report.json"
    report_path.write_text(
        json.dumps(
            {
                "status": "succeeded",
                "outputs": [
                    {
                        "kind": "preview",
                        "status": "succeeded",
                        "path": str(exported),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    (tmp_path / "input.mp4").write_bytes(b"video")

    with Session(engine) as session:
        session.add(
            Task(
                id="task-exported",
                name="Task Exported",
                status="succeeded",
                input_path=str(tmp_path / "input.mp4"),
                output_root=str(output_root),
                source_lang="zh",
                target_lang="en",
                config={
                    "pipeline": {
                        "template": "asr-dub-basic",
                        "run_to_stage": "task-g",
                        "video_source": "original",
                        "audio_source": "both",
                        "subtitle_source": "asr",
                        "output_intent": "dub_final",
                    },
                    "delivery": {
                        "export_preview": True,
                        "export_dub": False,
                        "subtitle_mode": "none",
                        "subtitle_render_source": "asr",
                    },
                },
                created_at=datetime.now(),
                updated_at=datetime.now(),
            )
        )
        session.commit()

    app.dependency_overrides[get_session] = _override_session(engine)
    try:
        client = TestClient(app)
        response = client.get("/api/tasks/task-exported")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["last_export_summary"]["status"] == "exported"
    assert len(payload["last_export_summary"]["files"]) == 1
    assert payload["last_export_summary"]["files"][0]["label"] == "正式成品"
    assert payload["last_export_summary"]["files"][0]["path"].endswith("final_preview.en.mp4")


def test_task_read_model_surfaces_transcription_correction_summary(tmp_path: Path) -> None:
    db_path = tmp_path / "task-read-correction.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)

    output_root = tmp_path / "output"
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
    (tmp_path / "input.mp4").write_bytes(b"video")

    with Session(engine) as session:
        session.add(
            Task(
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
        )
        session.commit()

    app.dependency_overrides[get_session] = _override_session(engine)
    try:
        client = TestClient(app)
        response = client.get("/api/tasks/task-correction-summary")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["transcription_correction_summary"]["corrected_count"] == 6
    assert payload["transcription_correction_summary"]["ocr_only_count"] == 1
    assert payload["transcription_correction_summary"]["algorithm_version"] == "ocr-guided-asr-correction-v1"
