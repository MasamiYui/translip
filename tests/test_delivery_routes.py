from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from translip.server.app import app
from translip.server.database import get_session
from translip.server.models import Task
from translip.types import ExportVideoArtifacts, ExportVideoRequest, ExportVideoResult


def test_delivery_routes_are_registered() -> None:
    client = TestClient(app)
    paths = {route.path for route in app.routes}
    assert "/api/tasks/{task_id}/subtitle-preview" in paths
    assert "/api/tasks/{task_id}/delivery-compose" in paths


def test_task_read_exposes_delivery_config(tmp_path: Path) -> None:
    db_path = tmp_path / "delivery-read.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        session.add(
            Task(
                id="task-read-delivery",
                name="Delivery Read",
                status="succeeded",
                input_path=str(tmp_path / "input.mp4"),
                output_root=str(tmp_path / "output"),
                source_lang="zh",
                target_lang="en",
                config={
                    "pipeline": {
                        "template": "asr-dub-basic",
                        "video_source": "original",
                        "audio_source": "both",
                        "subtitle_source": "asr",
                    },
                    "delivery": {
                        "subtitle_mode": "bilingual",
                        "subtitle_render_source": "ocr",
                        "subtitle_font": "Source Han Sans",
                    },
                },
                created_at=datetime.now(),
                updated_at=datetime.now(),
            )
        )
        session.commit()

    def override_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        client = TestClient(app)
        response = client.get("/api/tasks/task-read-delivery")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["config"]["template"] == "asr-dub-basic"
    assert payload["delivery_config"]["subtitle_mode"] == "bilingual"
    assert payload["delivery_config"]["subtitle_font"] == "Source Han Sans"


def test_delivery_compose_updates_delivery_config_only(tmp_path: Path, monkeypatch) -> None:
    from translip.server.routes import delivery as delivery_routes

    db_path = tmp_path / "delivery-compose.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)

    output_root = tmp_path / "output"
    output_root.mkdir()
    report_path = output_root / "task-g" / "delivery-report.json"
    report_path.parent.mkdir(parents=True)
    report_path.write_text(json.dumps({"status": "succeeded"}), encoding="utf-8")
    manifest_path = output_root / "task-g" / "delivery-manifest.json"
    manifest_path.write_text(json.dumps({"status": "succeeded"}), encoding="utf-8")
    preview_path = output_root / "task-g" / "final-preview.mp4"
    preview_path.write_bytes(b"preview")

    def fake_export_video(request: ExportVideoRequest) -> ExportVideoResult:
        return ExportVideoResult(
            request=request,
            artifacts=ExportVideoArtifacts(
                output_dir=request.output_dir,
                preview_video_path=preview_path,
                dub_video_path=None,
                manifest_path=manifest_path,
                report_path=report_path,
            ),
            manifest={"status": "succeeded", "request": asdict(request)},
            report={"status": "succeeded"},
        )

    monkeypatch.setattr(delivery_routes, "export_video", fake_export_video)

    with Session(engine) as session:
        session.add(
            Task(
                id="task-compose-delivery",
                name="Compose Delivery",
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
                        "subtitle_source": "asr",
                    },
                    "delivery": {
                        "subtitle_mode": "none",
                        "subtitle_render_source": "ocr",
                        "subtitle_font": "Noto Sans",
                    },
                },
                created_at=datetime.now(),
                updated_at=datetime.now(),
            )
        )
        session.commit()

    def override_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        client = TestClient(app)
        response = client.post(
            "/api/tasks/task-compose-delivery/delivery-compose",
            json={
                "subtitle_mode": "bilingual",
                "subtitle_source": "asr",
                "font_family": "Source Han Sans",
                "font_size": 42,
                "primary_color": "#FFEEAA",
                "outline_color": "#111111",
                "outline_width": 3,
                "position": "top",
                "margin_v": 22,
                "bold": True,
                "bilingual_chinese_position": "bottom",
                "bilingual_english_position": "top",
                "export_preview": True,
                "export_dub": False,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200

    with Session(engine) as session:
        task = session.get(Task, "task-compose-delivery")
        assert task is not None
        assert task.config["pipeline"]["video_source"] == "clean_if_available"
        assert task.config["pipeline"]["run_to_stage"] == "task-g"
        assert task.config["delivery"]["subtitle_mode"] == "bilingual"
        assert task.config["delivery"]["subtitle_render_source"] == "asr"
        assert task.config["delivery"]["subtitle_font"] == "Source Han Sans"
        assert task.config["delivery"]["export_dub"] is False
