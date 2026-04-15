from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from translip.server.app import app
from translip.server.database import get_session
from translip.server.models import Task


def test_task_manager_build_pipeline_request_keeps_external_roots(tmp_path: Path) -> None:
    from translip.server.task_manager import _build_pipeline_request

    task = Task(
        id="task-roots",
        name="Roots Task",
        status="pending",
        input_path=str(tmp_path / "input.mp4"),
        output_root=str(tmp_path / "output"),
        source_lang="zh",
        target_lang="en",
        config={
            "ocr_project_root": "/tmp/subtitle-ocr",
            "erase_project_root": "/tmp/video-subtitle-erasure",
        },
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )

    request = _build_pipeline_request(task)

    assert str(request.ocr_project_root) == "/tmp/subtitle-ocr"
    assert str(request.erase_project_root) == "/tmp/video-subtitle-erasure"


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
