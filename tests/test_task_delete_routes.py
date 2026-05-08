from __future__ import annotations

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


def _create_task(session: Session, *, task_id: str, output_root: Path) -> None:
    session.add(
        Task(
            id=task_id,
            name="Delete Me",
            status="succeeded",
            input_path=str(output_root.parent / "input.mp4"),
            output_root=str(output_root),
            source_lang="zh",
            target_lang="en",
            config={"pipeline": {"template": "asr-dub-basic"}},
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
    )
    session.commit()


def test_delete_task_removes_artifacts_by_default(tmp_path: Path) -> None:
    db_path = tmp_path / "task-delete-default.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)

    output_root = tmp_path / "output-pipeline" / "task-delete-default"
    output_root.mkdir(parents=True)
    (output_root / "final.mp4").write_bytes(b"artifact")
    with Session(engine) as session:
        _create_task(session, task_id="task-delete-default", output_root=output_root)

    app.dependency_overrides[get_session] = _override_session(engine)
    try:
        client = TestClient(app)
        response = client.delete("/api/tasks/task-delete-default")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert not output_root.exists()
    with Session(engine) as session:
        assert session.get(Task, "task-delete-default") is None


def test_delete_task_can_preserve_artifacts_when_explicitly_requested(tmp_path: Path) -> None:
    db_path = tmp_path / "task-delete-preserve.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)

    output_root = tmp_path / "output-pipeline" / "task-delete-preserve"
    output_root.mkdir(parents=True)
    (output_root / "final.mp4").write_bytes(b"artifact")
    with Session(engine) as session:
        _create_task(session, task_id="task-delete-preserve", output_root=output_root)

    app.dependency_overrides[get_session] = _override_session(engine)
    try:
        client = TestClient(app)
        response = client.delete(
            "/api/tasks/task-delete-preserve",
            params={"delete_artifacts": False},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert (output_root / "final.mp4").exists()
    with Session(engine) as session:
        assert session.get(Task, "task-delete-preserve") is None
