from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from translip.server.app import app
from translip.server.database import get_session
from translip.server.models import Task


def _seed_tasks(engine, tmp_path: Path) -> None:
    now = datetime.now()
    rows = [
        # Production-shape task: config is nested {pipeline: {...}, delivery: {...}}
        Task(
            id="task-dub-1",
            name="任务-12:10",
            status="succeeded",
            input_path=str(tmp_path / "a.mp4"),
            output_root=str(tmp_path / "out-a"),
            source_lang="zh",
            target_lang="en",
            config={"pipeline": {"template": "asr-dub-basic"}, "delivery": {}},
            created_at=now,
            updated_at=now,
        ),
        Task(
            id="task-dub-2",
            name="哪吒预告片0602",
            status="succeeded",
            input_path=str(tmp_path / "b.mp4"),
            output_root=str(tmp_path / "out-b"),
            source_lang="zh",
            target_lang="en",
            config={
                "pipeline": {
                    "template": "asr-dub+ocr-subs",
                    "output_intent": "bilingual_review",
                },
                "delivery": {},
            },
            created_at=now - timedelta(minutes=1),
            updated_at=now - timedelta(minutes=1),
        ),
        Task(
            id="task-commentary-1",
            name="解说预告0901",
            status="running",
            input_path=str(tmp_path / "c.mp4"),
            output_root=str(tmp_path / "out-c"),
            source_lang="zh",
            target_lang="zh",
            config={"pipeline": {"template": "asr-commentary"}, "delivery": {}},
            created_at=now - timedelta(minutes=2),
            updated_at=now - timedelta(minutes=2),
        ),
        Task(
            id="task-legacy",
            name="老任务-无模板",
            status="succeeded",
            input_path=str(tmp_path / "d.mp4"),
            output_root=str(tmp_path / "out-d"),
            source_lang="zh",
            target_lang="en",
            config={},  # legacy task: no pipeline/template key at all
            created_at=now - timedelta(minutes=3),
            updated_at=now - timedelta(minutes=3),
        ),
        # Edge case A: explicit output_intent says commentary even though the
        # template is NOT 'asr-commentary' (mis-configured/migrated row). Must
        # be classified as commentary to match the frontend IntentBadge.
        Task(
            id="task-commentary-by-intent",
            name="解说-显式intent",
            status="succeeded",
            input_path=str(tmp_path / "e.mp4"),
            output_root=str(tmp_path / "out-e"),
            source_lang="zh",
            target_lang="zh",
            config={
                "pipeline": {
                    "template": "asr-dub-basic",
                    "output_intent": "commentary_recap",
                },
                "delivery": {},
            },
            created_at=now - timedelta(minutes=4),
            updated_at=now - timedelta(minutes=4),
        ),
        # Edge case B: template IS 'asr-commentary' but explicit output_intent
        # is 'dub_final' (this is what the real DB has, b/c the create flow
        # writes a default output_intent='dub_final' alongside the commentary
        # template). Must still be classified as commentary.
        Task(
            id="task-commentary-with-stale-intent",
            name="解说-旧intent残留",
            status="succeeded",
            input_path=str(tmp_path / "f.mp4"),
            output_root=str(tmp_path / "out-f"),
            source_lang="zh",
            target_lang="zh",
            config={
                "pipeline": {
                    "template": "asr-commentary",
                    "output_intent": "dub_final",
                },
                "delivery": {},
            },
            created_at=now - timedelta(minutes=5),
            updated_at=now - timedelta(minutes=5),
        ),
        # Edge case C: very old flat-shape config (no pipeline wrapper). The
        # SQL filter must still pick it up via the $.template fallback so old
        # rows don't disappear when filtering.
        Task(
            id="task-commentary-flat-shape",
            name="解说-扁平config",
            status="succeeded",
            input_path=str(tmp_path / "g.mp4"),
            output_root=str(tmp_path / "out-g"),
            source_lang="zh",
            target_lang="zh",
            config={"template": "asr-commentary"},
            created_at=now - timedelta(minutes=6),
            updated_at=now - timedelta(minutes=6),
        ),
    ]
    with Session(engine) as session:
        for r in rows:
            session.add(r)
        session.commit()


@pytest.fixture()
def client_with_seed(tmp_path: Path):
    db_path = tmp_path / "tasks.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    _seed_tasks(engine, tmp_path)

    def override_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_list_tasks_default_returns_all(client_with_seed: TestClient) -> None:
    resp = client_with_seed.get("/api/tasks")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 7
    assert {item["id"] for item in body["items"]} == {
        "task-dub-1",
        "task-dub-2",
        "task-commentary-1",
        "task-legacy",
        "task-commentary-by-intent",
        "task-commentary-with-stale-intent",
        "task-commentary-flat-shape",
    }


def test_list_tasks_intent_commentary_only(client_with_seed: TestClient) -> None:
    resp = client_with_seed.get("/api/tasks", params={"intent": "commentary"})
    assert resp.status_code == 200
    body = resp.json()
    # All 4 commentary rows: by-template (nested), by-explicit-intent,
    # template-with-stale-intent, and the flat-shape legacy commentary row.
    assert body["total"] == 4
    assert {item["id"] for item in body["items"]} == {
        "task-commentary-1",
        "task-commentary-by-intent",
        "task-commentary-with-stale-intent",
        "task-commentary-flat-shape",
    }
    # And the read model reports them all as commentary_recap for the frontend.
    for item in body["items"]:
        assert item["output_intent"] == "commentary_recap"


def test_list_tasks_intent_dub_includes_legacy_without_template(
    client_with_seed: TestClient,
) -> None:
    resp = client_with_seed.get("/api/tasks", params={"intent": "dub"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    ids = {item["id"] for item in body["items"]}
    assert ids == {"task-dub-1", "task-dub-2", "task-legacy"}
    for item in body["items"]:
        assert item["output_intent"] != "commentary_recap"


def test_list_tasks_intent_all_is_equivalent_to_default(
    client_with_seed: TestClient,
) -> None:
    resp = client_with_seed.get("/api/tasks", params={"intent": "all"})
    assert resp.status_code == 200
    assert resp.json()["total"] == 7


def test_list_tasks_intent_invalid_returns_422(client_with_seed: TestClient) -> None:
    resp = client_with_seed.get("/api/tasks", params={"intent": "garbage"})
    assert resp.status_code == 422
    assert "intent" in resp.json()["detail"].lower() or "garbage" in resp.json()["detail"]


def test_list_tasks_intent_combines_with_status(client_with_seed: TestClient) -> None:
    resp = client_with_seed.get(
        "/api/tasks",
        params={"intent": "dub", "status": "succeeded"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert {item["id"] for item in body["items"]} == {
        "task-dub-1",
        "task-dub-2",
        "task-legacy",
    }

    resp_running = client_with_seed.get(
        "/api/tasks",
        params={"intent": "commentary", "status": "running"},
    )
    assert resp_running.status_code == 200
    assert resp_running.json()["total"] == 1


# -- Regression tests for the cross-field consistency bug ---------------------


def test_intent_commentary_recognized_by_explicit_output_intent(
    client_with_seed: TestClient,
) -> None:
    """A task whose pipeline.template is NOT 'asr-commentary' but whose
    pipeline.output_intent is 'commentary_recap' must still be classified as
    commentary, so the frontend badge and the backend filter agree."""
    resp = client_with_seed.get("/api/tasks", params={"intent": "commentary"})
    body = resp.json()
    ids = {item["id"] for item in body["items"]}
    assert "task-commentary-by-intent" in ids

    resp_dub = client_with_seed.get("/api/tasks", params={"intent": "dub"})
    dub_ids = {item["id"] for item in resp_dub.json()["items"]}
    assert "task-commentary-by-intent" not in dub_ids


def test_intent_commentary_wins_over_stale_dub_final_intent(
    client_with_seed: TestClient,
) -> None:
    """A task whose pipeline.template IS 'asr-commentary' but whose stored
    output_intent is the default 'dub_final' (this is what the real create
    flow writes) must still be classified as commentary — driven by the
    template, not the stale explicit intent. Mirrors infer_output_intent."""
    resp = client_with_seed.get("/api/tasks", params={"intent": "commentary"})
    body = resp.json()
    ids = {item["id"] for item in body["items"]}
    assert "task-commentary-with-stale-intent" in ids

    resp_dub = client_with_seed.get("/api/tasks", params={"intent": "dub"})
    dub_ids = {item["id"] for item in resp_dub.json()["items"]}
    assert "task-commentary-with-stale-intent" not in dub_ids


def test_intent_commentary_handles_legacy_flat_config_shape(
    client_with_seed: TestClient,
) -> None:
    """Old tasks may have been persisted with a flat config ({"template": ...})
    instead of the nested {pipeline: {...}} shape. The SQL filter must still
    classify them correctly via the $.template fallback."""
    resp = client_with_seed.get("/api/tasks", params={"intent": "commentary"})
    ids = {item["id"] for item in resp.json()["items"]}
    assert "task-commentary-flat-shape" in ids
