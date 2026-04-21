from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from translip.server.app import app
from translip.server.database import get_session
from translip.server.models import Task


def test_speaker_review_route_generates_diagnostics_and_plan(tmp_path: Path) -> None:
    engine = _test_engine(tmp_path, "speaker-review.db")
    output_root = tmp_path / "output"
    _write_segments_fixture(output_root)
    _insert_task(engine, output_root)

    def override_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        client = TestClient(app)
        response = client.get("/api/tasks/task-speaker-review/speaker-review")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "available"
    assert payload["summary"]["speaker_count"] == 3
    assert payload["summary"]["high_risk_speaker_count"] >= 1
    assert payload["speakers"][0]["speaker_label"].startswith("SPEAKER_")
    assert (output_root / "asr-ocr-correct" / "voice" / "speaker_diagnostics.zh.json").exists()
    assert (output_root / "asr-ocr-correct" / "voice" / "speaker_review_plan.zh.json").exists()


def test_speaker_review_decision_and_apply_routes_write_corrected_segments(tmp_path: Path) -> None:
    engine = _test_engine(tmp_path, "speaker-review-apply.db")
    output_root = tmp_path / "output"
    _write_segments_fixture(output_root)
    _insert_task(engine, output_root)

    def override_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        client = TestClient(app)
        decision_response = client.post(
            "/api/tasks/task-speaker-review/speaker-review/decisions",
            json={
                "item_id": "segment:seg-0002",
                "item_type": "segment",
                "decision": "relabel_to_previous_speaker",
                "source_speaker_label": "SPEAKER_01",
                "segment_ids": ["seg-0002"],
            },
        )
        apply_response = client.post("/api/tasks/task-speaker-review/speaker-review/apply")
    finally:
        app.dependency_overrides.clear()

    assert decision_response.status_code == 200
    assert apply_response.status_code == 200
    corrected_path = output_root / "asr-ocr-correct" / "voice" / "segments.zh.speaker-corrected.json"
    payload = json.loads(corrected_path.read_text(encoding="utf-8"))
    assert payload["segments"][1]["speaker_label"] == "SPEAKER_00"
    assert payload["segments"][1]["original_speaker_label"] == "SPEAKER_01"
    assert (output_root / "asr-ocr-correct" / "voice" / "segments.zh.speaker-corrected.srt").exists()
    assert (output_root / "asr-ocr-correct" / "voice" / "speaker-review-manifest.json").exists()


def _test_engine(tmp_path: Path, name: str):
    engine = create_engine(
        f"sqlite:///{tmp_path / name}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    return engine


def _insert_task(engine, output_root: Path) -> None:
    with Session(engine) as session:
        session.add(
            Task(
                id="task-speaker-review",
                name="Speaker Review",
                status="succeeded",
                input_path=str(output_root / "input.mp4"),
                output_root=str(output_root),
                source_lang="zh",
                target_lang="en",
                config={"pipeline": {"template": "asr-dub-basic"}},
                created_at=datetime.now(),
                updated_at=datetime.now(),
            )
        )
        session.commit()


def _write_segments_fixture(output_root: Path) -> None:
    path = output_root / "asr-ocr-correct" / "voice" / "segments.zh.corrected.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "segments": [
                    {"id": "seg-0001", "start": 0.0, "end": 1.8, "duration": 1.8, "text": "第一句", "speaker_label": "SPEAKER_00", "language": "zh"},
                    {"id": "seg-0002", "start": 1.86, "end": 2.46, "duration": 0.6, "text": "插一句", "speaker_label": "SPEAKER_01", "language": "zh"},
                    {"id": "seg-0003", "start": 2.5, "end": 4.0, "duration": 1.5, "text": "继续说话", "speaker_label": "SPEAKER_00", "language": "zh"},
                    {"id": "seg-0004", "start": 4.6, "end": 24.8, "duration": 20.2, "text": "您好", "speaker_label": "SPEAKER_02", "language": "zh"},
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
