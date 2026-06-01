from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

import translip.server.routes.analysis as analysis_route
from translip.server.app import app
from translip.server.database import get_session
from translip.server.models import Analysis, Task


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _make_pipeline(root: Path) -> None:
    tc = root / "task-c" / "voice" / "clip"
    _write(tc / "translation.en.json", {"segments": [
        {"segment_id": "s1", "speaker_label": "SPK1", "start": 0.0, "end": 2.0,
         "source_text": "你好", "target_text": "Hello"},
    ]})
    td = root / "task-d" / "voice" / "clip"
    _write(td / "dub_report.en.json", {"segments": [{"segment_id": "s1", "backread_text": "hello"}]})
    _write(root / "task-e" / "voice" / "mix_report.en.json", {
        "input": {"translation_path": str(tc / "translation.en.json"),
                  "task_d_report_paths": [str(td / "dub_report.en.json")]},
        "stats": {"placed_count": 1, "skipped_count": 1, "skip_reason_counts": {"skipped_missing_audio": 1},
                  "quality_summary": {"total_count": 2, "overall_status_counts": {"passed": 1}}},
        "placed_segments": [{"segment_id": "s1", "anchor_start": 0.0, "anchor_end": 2.0,
                             "target_text": "Hello", "audio_path": str(td / "s1.wav"),
                             "task_d_report_path": str(td / "dub_report.en.json"),
                             "mix_status": "placed", "overall_status": "passed",
                             "speaker_status": "passed", "intelligibility_status": "passed",
                             "duration_status": "passed", "subtitle_coverage_ratio": 0.9}],
        "skipped_segments": [{"segment_id": "s2", "anchor_start": 2.0, "anchor_end": 4.0,
                              "target_text": "Dropped", "mix_status": "skipped_missing_audio"}],
    })


def _task(output_root: Path) -> Task:
    return Task(
        id="task-analysis",
        name="analysis-fixture",
        status="succeeded",
        input_path=str(output_root / "input.mp4"),
        output_root=str(output_root),
        source_lang="zh",
        target_lang="en",
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )


def test_dub_qa_analysis_route_end_to_end(tmp_path: Path, monkeypatch) -> None:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'analysis.db'}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    # The daemon worker uses the module-global engine; point it at the test DB.
    monkeypatch.setattr(analysis_route, "engine", engine)

    output_root = tmp_path / "output"
    _make_pipeline(output_root)
    with Session(engine) as session:
        session.add(_task(output_root))
        session.commit()

    def override_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        client = TestClient(app)
        create = client.post("/api/tasks/task-analysis/analyses/dub-qa", json={"run_translation_judge": False})
        assert create.status_code == 200, create.text
        analysis_id = create.json()["id"]

        # Poll until the daemon thread finishes.
        deadline = time.time() + 15
        status = "pending"
        while time.time() < deadline:
            detail = client.get(f"/api/tasks/task-analysis/analyses/{analysis_id}")
            assert detail.status_code == 200
            status = detail.json()["status"]
            if status in ("succeeded", "failed"):
                break
            time.sleep(0.1)
        assert status == "succeeded", detail.text

        summary = detail.json()["result"]
        assert summary["issue_counts"]["undubbed"] == 1
        assert detail.json()["report_path"]

        listing = client.get("/api/tasks/task-analysis/analyses")
        assert listing.status_code == 200
        assert len(listing.json()) == 1

        report = client.get(f"/api/tasks/task-analysis/analyses/{analysis_id}/report")
        assert report.status_code == 200
        rows = {row["segment_id"]: row for row in report.json()["segments"]}
        assert rows["s1"]["source_text"] == "你好"
        assert rows["s2"]["issue_tags"] == ["undubbed"]
        # dub audio path is relative to output_root for the artifacts endpoint.
        assert rows["s1"]["dub_audio_path"] == "task-d/voice/clip/s1.wav"
    finally:
        app.dependency_overrides.clear()


def test_create_returns_existing_in_flight_analysis(tmp_path: Path, monkeypatch) -> None:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'analysis.db'}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(analysis_route, "engine", engine)

    output_root = tmp_path / "output"
    _make_pipeline(output_root)
    with Session(engine) as session:
        session.add(_task(output_root))
        # An analysis is already running for this task.
        session.add(Analysis(id="ana-running", task_id="task-analysis", analysis_type="dub-qa",
                             status="running", target_lang="en", source_lang="zh", params={}))
        session.commit()

    def override_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        client = TestClient(app)
        resp = client.post("/api/tasks/task-analysis/analyses/dub-qa", json={"run_translation_judge": False})
        assert resp.status_code == 200
        # Returns the existing in-flight run instead of spawning a duplicate.
        assert resp.json()["id"] == "ana-running"
        assert len(client.get("/api/tasks/task-analysis/analyses").json()) == 1
    finally:
        app.dependency_overrides.clear()


def test_deleting_task_cleans_up_its_analyses(tmp_path: Path, monkeypatch) -> None:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'analysis.db'}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(analysis_route, "engine", engine)

    output_root = tmp_path / "output"
    _make_pipeline(output_root)
    with Session(engine) as session:
        session.add(_task(output_root))
        session.add(Analysis(id="ana-keep", task_id="task-analysis", analysis_type="dub-qa",
                             status="succeeded", target_lang="en", source_lang="zh", params={}))
        session.commit()

    def override_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        client = TestClient(app)
        resp = client.delete("/api/tasks/task-analysis", params={"delete_artifacts": False})
        assert resp.status_code == 200
        with Session(engine) as session:
            assert session.get(Analysis, "ana-keep") is None
    finally:
        app.dependency_overrides.clear()
