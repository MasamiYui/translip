from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from translip.server.app import app
from translip.server.database import get_session
from translip.server.models import Task, TaskStage


def test_task_manager_build_pipeline_request_reads_erase_params(tmp_path: Path) -> None:
    from translip.server.task_manager import _build_pipeline_request

    task = Task(
        id="task-erase",
        name="Erase Task",
        status="pending",
        input_path=str(tmp_path / "input.mp4"),
        output_root=str(tmp_path / "output"),
        source_lang="zh",
        target_lang="en",
        config={
            "erase_backend": "lama",
            "erase_device": "cpu",
            "erase_max_load": 24,
        },
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )

    request = _build_pipeline_request(task)

    assert request.erase_backend == "lama"
    assert request.erase_device == "cpu"
    assert request.erase_max_load == 24


def test_stop_task_signals_registered_cancel_event(tmp_path: Path) -> None:
    import threading

    from translip.server import task_manager as tm
    from translip.server.task_manager import TaskManager

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        task = Task(
            id="task-cancel",
            name="Cancel Task",
            status="running",
            input_path=str(tmp_path / "in.mp4"),
            output_root=str(tmp_path / "out"),
            source_lang="zh",
            target_lang="en",
            config={},
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        session.add(task)
        session.commit()

        event = threading.Event()
        with tm._cancel_events_lock:
            tm._cancel_events["task-cancel"] = event
        try:
            stopped = TaskManager().stop_task(session, "task-cancel")
        finally:
            with tm._cancel_events_lock:
                tm._cancel_events.pop("task-cancel", None)

        assert stopped is True
        assert event.is_set() is True
        session.refresh(task)
        assert task.status == "failed"
        assert task.error_message == "Stopped by user"


def test_mark_interrupted_tasks_flips_orphaned_running_and_pending(tmp_path: Path, monkeypatch) -> None:
    from translip.server import task_manager as tm

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(tm, "engine", engine)
    with Session(engine) as session:
        for tid, status in (("t-run", "running"), ("t-pend", "pending"), ("t-done", "succeeded")):
            session.add(
                Task(
                    id=tid,
                    name=tid,
                    status=status,
                    input_path=str(tmp_path / "in.mp4"),
                    output_root=str(tmp_path / tid),
                    source_lang="zh",
                    target_lang="en",
                    config={},
                    created_at=datetime.now(),
                    updated_at=datetime.now(),
                )
            )
        session.commit()

    count = tm.mark_interrupted_tasks()

    assert count == 2
    with Session(engine) as session:
        assert session.get(Task, "t-run").status == "interrupted"
        assert session.get(Task, "t-pend").status == "interrupted"
        assert session.get(Task, "t-done").status == "succeeded"


def test_build_workflow_graph_payload_returns_nodes_and_edges() -> None:
    from translip.orchestration.graph_export import build_workflow_graph_payload

    payload = build_workflow_graph_payload(
        {
            "template_id": "asr-dub+ocr-subs",
            "status": "running",
            "nodes": [
                {"node_name": "stage1", "status": "succeeded"},
                {"node_name": "task-a", "status": "running"},
            ],
        }
    )

    assert payload["workflow"]["template_id"] == "asr-dub+ocr-subs"
    assert payload["nodes"][2]["id"] == "task-a"
    assert payload["edges"][0]["from"] == "stage1"


def test_task_graph_endpoint_returns_nodes_and_edges(tmp_path: Path) -> None:
    db_path = tmp_path / "graph.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)

    task_id = "task-graph-1"
    output_root = tmp_path / task_id
    output_root.mkdir(parents=True)
    (output_root / "workflow-manifest.json").write_text(
        json.dumps(
            {
                "template_id": "asr-dub+ocr-subs",
                "status": "running",
                "nodes": [
                    {"node_name": "stage1", "status": "succeeded"},
                    {"node_name": "task-a", "status": "running"},
                ],
            }
        ),
        encoding="utf-8",
    )

    with Session(engine) as session:
        session.add(
            Task(
                id=task_id,
                name="Graph Task",
                status="running",
                input_path=str(tmp_path / "input.mp4"),
                output_root=str(output_root),
                source_lang="zh",
                target_lang="en",
                config={},
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
        response = client.get(f"/api/tasks/{task_id}/graph")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["workflow"]["template_id"] == "asr-dub+ocr-subs"
    assert payload["nodes"][2]["id"] == "task-a"
    assert payload["edges"][0]["to"] == "task-a"


def test_task_graph_endpoint_falls_back_to_db_stages_while_running(tmp_path: Path) -> None:
    db_path = tmp_path / "graph-fallback.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)

    task_id = "task-graph-fallback"
    output_root = tmp_path / task_id
    output_root.mkdir(parents=True)

    with Session(engine) as session:
        session.add(
            Task(
                id=task_id,
                name="Graph Fallback Task",
                status="running",
                input_path=str(tmp_path / "input.mp4"),
                output_root=str(output_root),
                source_lang="zh",
                target_lang="en",
                config={"template": "asr-dub+ocr-subs"},
                created_at=datetime.now(),
                updated_at=datetime.now(),
            )
        )
        session.add(TaskStage(task_id=task_id, stage_name="stage1", status="succeeded"))
        session.add(TaskStage(task_id=task_id, stage_name="task-a", status="running", progress_percent=42.0))
        session.commit()

    def override_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        client = TestClient(app)
        response = client.get(f"/api/tasks/{task_id}/graph")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["workflow"]["template_id"] == "asr-dub+ocr-subs"
    assert payload["workflow"]["status"] == "running"
    assert payload["nodes"][0]["status"] == "succeeded"
    assert payload["nodes"][2]["status"] == "running"
    assert payload["nodes"][2]["progress_percent"] == 42.0


def test_stage_manifest_endpoint_supports_ocr_nodes(tmp_path: Path) -> None:
    db_path = tmp_path / "graph.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)

    task_id = "task-graph-ocr"
    output_root = tmp_path / task_id
    output_root.mkdir(parents=True)
    manifest_path = output_root / "ocr-detect" / "ocr-detect-manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps({"status": "succeeded"}), encoding="utf-8")

    with Session(engine) as session:
        session.add(
            Task(
                id=task_id,
                name="Graph OCR Task",
                status="succeeded",
                input_path=str(tmp_path / "input.mp4"),
                output_root=str(output_root),
                source_lang="zh",
                target_lang="en",
                config={},
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
        response = client.get(f"/api/tasks/{task_id}/stages/ocr-detect/manifest")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["status"] == "succeeded"
