from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from translip.server.app import app
from translip.server.database import get_session
from translip.server.models import Task


TASK_ID = "task-personas"


def test_persona_crud_and_review_injection(tmp_path: Path) -> None:
    client, output_root = _bootstrap(tmp_path, "personas-crud.db")
    try:
        review = client.get(f"/api/tasks/{TASK_ID}/speaker-review").json()
        assert review["status"] == "available"
        assert "personas" in review
        bundle = review["personas"]
        assert isinstance(bundle["items"], list)
        assert review["summary"]["unnamed_speaker_count"] >= 1

        created = client.post(
            f"/api/tasks/{TASK_ID}/speaker-review/personas",
            json={"name": "小明", "bindings": ["SPEAKER_00"]},
        )
        assert created.status_code == 200, created.text
        body = created.json()
        assert body["ok"] is True
        persona = body["persona"]
        assert persona["name"] == "小明"
        assert "SPEAKER_00" in persona["bindings"]
        pid = persona["id"]

        listed = client.get(f"/api/tasks/{TASK_ID}/speaker-review/personas").json()
        assert any(p["id"] == pid for p in listed["items"])
        assert listed["by_speaker"]["SPEAKER_00"]["name"] == "小明"

        renamed = client.patch(
            f"/api/tasks/{TASK_ID}/speaker-review/personas/{pid}",
            json={"name": "小明（旁白）"},
        )
        assert renamed.status_code == 200
        assert renamed.json()["persona"]["name"] == "小明（旁白）"

        bind = client.post(
            f"/api/tasks/{TASK_ID}/speaker-review/personas/{pid}/bind",
            json={"speaker": "SPEAKER_02"},
        )
        assert bind.status_code == 200
        assert "SPEAKER_02" in bind.json()["persona"]["bindings"]

        unbind = client.post(
            f"/api/tasks/{TASK_ID}/speaker-review/personas/{pid}/unbind",
            json={"speaker": "SPEAKER_02"},
        )
        assert unbind.status_code == 200
        assert "SPEAKER_02" not in unbind.json()["persona"]["bindings"]

        review2 = client.get(f"/api/tasks/{TASK_ID}/speaker-review").json()
        assert review2["summary"]["unnamed_speaker_count"] < review["summary"]["unnamed_speaker_count"]
        assert review2["personas"]["by_speaker"]["SPEAKER_00"]["name"] == "小明（旁白）"

        deleted = client.delete(
            f"/api/tasks/{TASK_ID}/speaker-review/personas/{pid}"
        )
        assert deleted.status_code == 200
        assert all(p["id"] != pid for p in deleted.json()["personas"]["items"])
    finally:
        app.dependency_overrides.clear()


def test_persona_bulk_and_undo(tmp_path: Path) -> None:
    client, _ = _bootstrap(tmp_path, "personas-bulk.db")
    try:
        bulk = client.post(
            f"/api/tasks/{TASK_ID}/speaker-review/personas/bulk",
            json={"template": "by_index"},
        )
        assert bulk.status_code == 200, bulk.text
        body = bulk.json()
        created = body["created"]
        assert len(created) >= 3
        assert all(p["name"].startswith("说话人") for p in created)

        review = client.get(f"/api/tasks/{TASK_ID}/speaker-review").json()
        assert review["personas"]["by_speaker"]["SPEAKER_00"]["name"].startswith("说话人")

        undo = client.post(f"/api/tasks/{TASK_ID}/speaker-review/personas/undo")
        assert undo.status_code == 200
        review_after = client.get(f"/api/tasks/{TASK_ID}/speaker-review").json()
        assert review_after["summary"]["unnamed_speaker_count"] >= review["summary"]["unnamed_speaker_count"]
    finally:
        app.dependency_overrides.clear()


def test_persona_suggest_endpoint(tmp_path: Path) -> None:
    client, _ = _bootstrap(tmp_path, "personas-suggest.db", with_named_lines=True)
    try:
        sugg = client.post(
            f"/api/tasks/{TASK_ID}/speaker-review/personas/suggest",
            json={"speakers": None},
        )
        assert sugg.status_code == 200, sugg.text
        suggestions = sugg.json()["suggestions"]
        assert "SPEAKER_00" in suggestions
        candidates = suggestions["SPEAKER_00"]
        assert any(c["name"] == "小明" for c in candidates)
    finally:
        app.dependency_overrides.clear()


def test_apply_decisions_sync_persona_into_corrected(tmp_path: Path) -> None:
    client, output_root = _bootstrap(tmp_path, "personas-apply.db")
    try:
        client.post(
            f"/api/tasks/{TASK_ID}/speaker-review/personas",
            json={"name": "主持人", "bindings": ["SPEAKER_00"]},
        )
        client.post(
            f"/api/tasks/{TASK_ID}/speaker-review/personas",
            json={"name": "嘉宾", "bindings": ["SPEAKER_01"]},
        )
        merge = client.post(
            f"/api/tasks/{TASK_ID}/speaker-review/decisions",
            json={
                "item_id": "speaker:SPEAKER_02",
                "item_type": "speaker_profile",
                "decision": "merge_speaker",
                "payload": {"target_speaker": "SPEAKER_00", "source_speaker": "SPEAKER_02"},
            },
        )
        assert merge.status_code == 200, merge.text

        applied = client.post(f"/api/tasks/{TASK_ID}/speaker-review/apply")
        assert applied.status_code == 200, applied.text

        corrected_path = (
            output_root
            / "asr-ocr-correct"
            / "voice"
            / "segments.zh.speaker-corrected.json"
        )
        payload = json.loads(corrected_path.read_text(encoding="utf-8"))
        seg = payload["segments"][0]
        assert seg.get("persona_name") == "主持人"
        assert seg.get("persona_id")

        srt_path = (
            output_root
            / "asr-ocr-correct"
            / "voice"
            / "segments.zh.speaker-corrected.srt"
        )
        srt = srt_path.read_text(encoding="utf-8")
        assert "[主持人]" in srt
    finally:
        app.dependency_overrides.clear()


def _bootstrap(tmp_path: Path, db_name: str, *, with_named_lines: bool = False):
    engine = create_engine(
        f"sqlite:///{tmp_path / db_name}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    output_root = tmp_path / "output"
    _write_segments_fixture(output_root, with_named_lines=with_named_lines)
    with Session(engine) as session:
        session.add(
            Task(
                id=TASK_ID,
                name="Speaker Personas",
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

    def override_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    client = TestClient(app)
    return client, output_root


def _write_segments_fixture(output_root: Path, *, with_named_lines: bool = False) -> None:
    path = output_root / "asr-ocr-correct" / "voice" / "segments.zh.corrected.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    speaker0_text = "我是小明，请多关照" if with_named_lines else "第一句"
    path.write_text(
        json.dumps(
            {
                "segments": [
                    {
                        "id": "seg-0001",
                        "start": 0.0,
                        "end": 1.8,
                        "duration": 1.8,
                        "text": speaker0_text,
                        "speaker_label": "SPEAKER_00",
                        "language": "zh",
                    },
                    {
                        "id": "seg-0002",
                        "start": 1.86,
                        "end": 2.46,
                        "duration": 0.6,
                        "text": "插一句",
                        "speaker_label": "SPEAKER_01",
                        "language": "zh",
                    },
                    {
                        "id": "seg-0003",
                        "start": 2.5,
                        "end": 4.0,
                        "duration": 1.5,
                        "text": "继续说话",
                        "speaker_label": "SPEAKER_00",
                        "language": "zh",
                    },
                    {
                        "id": "seg-0004",
                        "start": 4.6,
                        "end": 24.8,
                        "duration": 20.2,
                        "text": "您好",
                        "speaker_label": "SPEAKER_02",
                        "language": "zh",
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_persona_name_conflict_409_and_force(tmp_path: Path) -> None:
    client, _ = _bootstrap(tmp_path, "personas-conflict.db")
    try:
        first = client.post(
            f"/api/tasks/{TASK_ID}/speaker-review/personas",
            json={"name": "小明", "bindings": ["SPEAKER_00"]},
        )
        assert first.status_code == 200

        conflict = client.post(
            f"/api/tasks/{TASK_ID}/speaker-review/personas",
            json={"name": "小明", "bindings": ["SPEAKER_01"]},
        )
        assert conflict.status_code == 409
        body = conflict.json()["detail"]
        assert body["code"] == "persona_name_conflict"
        assert body["existing_id"]
        assert body["existing_name"] == "小明"

        forced = client.post(
            f"/api/tasks/{TASK_ID}/speaker-review/personas",
            json={"name": "小明", "bindings": ["SPEAKER_01"], "force": True},
        )
        assert forced.status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_persona_update_name_conflict_409(tmp_path: Path) -> None:
    client, _ = _bootstrap(tmp_path, "personas-update-conflict.db")
    try:
        a = client.post(
            f"/api/tasks/{TASK_ID}/speaker-review/personas",
            json={"name": "小明", "bindings": ["SPEAKER_00"]},
        ).json()["persona"]
        b = client.post(
            f"/api/tasks/{TASK_ID}/speaker-review/personas",
            json={"name": "小红", "bindings": ["SPEAKER_01"]},
        ).json()["persona"]
        conflict = client.patch(
            f"/api/tasks/{TASK_ID}/speaker-review/personas/{b['id']}",
            json={"name": "小明"},
        )
        assert conflict.status_code == 409
        body = conflict.json()["detail"]
        assert body["existing_id"] == a["id"]
    finally:
        app.dependency_overrides.clear()


def test_persona_history_redo_and_status(tmp_path: Path) -> None:
    client, _ = _bootstrap(tmp_path, "personas-redo.db")
    try:
        created = client.post(
            f"/api/tasks/{TASK_ID}/speaker-review/personas",
            json={"name": "小明", "bindings": ["SPEAKER_00"]},
        ).json()["persona"]

        client.patch(
            f"/api/tasks/{TASK_ID}/speaker-review/personas/{created['id']}",
            json={"name": "小明二号"},
        )

        history_before = client.get(f"/api/tasks/{TASK_ID}/speaker-review/personas/history")
        assert history_before.status_code == 200
        status_before = history_before.json()["history"]
        assert status_before["can_undo"] is True

        undo = client.post(f"/api/tasks/{TASK_ID}/speaker-review/personas/undo")
        assert undo.status_code == 200
        after_undo = client.get(f"/api/tasks/{TASK_ID}/speaker-review/personas").json()
        current = [p for p in after_undo["items"] if p["id"] == created["id"]]
        assert current and current[0]["name"] == "小明"

        redo = client.post(f"/api/tasks/{TASK_ID}/speaker-review/personas/redo")
        assert redo.status_code == 200
        after_redo = client.get(f"/api/tasks/{TASK_ID}/speaker-review/personas").json()
        current2 = [p for p in after_redo["items"] if p["id"] == created["id"]]
        assert current2 and current2[0]["name"] == "小明二号"
    finally:
        app.dependency_overrides.clear()


def test_persona_snapshot_written_on_create(tmp_path: Path) -> None:
    client, output_root = _bootstrap(tmp_path, "personas-snapshot.db")
    try:
        client.post(
            f"/api/tasks/{TASK_ID}/speaker-review/personas",
            json={"name": "小明", "bindings": ["SPEAKER_00"]},
        )
        client.post(
            f"/api/tasks/{TASK_ID}/speaker-review/personas",
            json={"name": "小红", "bindings": ["SPEAKER_01"]},
        )
        review_dir = output_root / "asr-ocr-correct" / "voice"
        snap_dir = review_dir / "speaker-personas.snapshots"
        assert snap_dir.exists()
        snaps = list(snap_dir.glob("*.json"))
        assert len(snaps) >= 1
    finally:
        app.dependency_overrides.clear()


def test_apply_preview_returns_summary_and_samples(tmp_path: Path) -> None:
    client, _ = _bootstrap(tmp_path, "personas-preview.db")
    try:
        client.post(
            f"/api/tasks/{TASK_ID}/speaker-review/personas",
            json={"name": "主持人", "bindings": ["SPEAKER_00"]},
        )
        client.post(
            f"/api/tasks/{TASK_ID}/speaker-review/decisions",
            json={
                "item_id": "speaker:SPEAKER_02",
                "item_type": "speaker_profile",
                "decision": "merge_speaker",
                "payload": {"target_speaker": "SPEAKER_00", "source_speaker": "SPEAKER_02"},
            },
        )
        preview = client.post(f"/api/tasks/{TASK_ID}/speaker-review/apply-preview")
        assert preview.status_code == 200, preview.text
        body = preview.json()
        assert body["ok"] is True
        summary = body["summary"]
        assert summary["total_segments"] >= 1
        assert "changed_segments" in summary
        assert "unassigned_segments" in summary
        assert "personas_used" in summary
        assert "merges" in summary
        assert "sample_changes" in body
        assert isinstance(body["sample_changes"], list)
        assert len(body["sample_changes"]) <= 50
    finally:
        app.dependency_overrides.clear()


def test_persona_tts_voice_fields_round_trip(tmp_path: Path) -> None:
    client, _ = _bootstrap(tmp_path, "personas-tts.db")
    try:
        created = client.post(
            f"/api/tasks/{TASK_ID}/speaker-review/personas",
            json={
                "name": "配音员A",
                "bindings": ["SPEAKER_00"],
                "tts_voice_id": "voice-xyz",
                "tts_skip": False,
                "gender": "female",
                "role": "narrator",
            },
        ).json()["persona"]
        assert created["tts_voice_id"] == "voice-xyz"
        assert created.get("gender") == "female"
        assert created.get("role") == "narrator"

        updated = client.patch(
            f"/api/tasks/{TASK_ID}/speaker-review/personas/{created['id']}",
            json={"tts_voice_id": "", "tts_skip": True},
        ).json()["persona"]
        assert updated.get("tts_voice_id") in (None, "")
        assert updated.get("tts_skip") is True
    finally:
        app.dependency_overrides.clear()


# ---------- Global persona library (phase B) ----------


def test_global_personas_import_list_delete(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("TRANSLIP_GLOBAL_PERSONAS_DIR", str(tmp_path / "global"))
    client, _ = _bootstrap(tmp_path, "global-crud.db")
    try:
        listed0 = client.get("/api/global-personas").json()
        assert listed0["ok"] is True
        assert listed0["personas"] == []

        payload = {
            "personas": [
                {"id": "g-001", "name": "旁白老王", "role": "narrator", "gender": "male"},
                {"id": "g-002", "name": "女主小美", "role": "protagonist", "gender": "female"},
            ]
        }
        resp = client.post("/api/global-personas/import", json=payload)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["ok"] is True
        assert body["accepted"] == 2
        assert body["total"] == 2

        listed = client.get("/api/global-personas").json()
        assert len(listed["personas"]) == 2
        persona_names = {p["name"] for p in listed["personas"]}
        assert persona_names == {"旁白老王", "女主小美"}

        target_id = listed["personas"][0]["id"]
        del_resp = client.delete(f"/api/global-personas/{target_id}")
        assert del_resp.status_code == 200
        assert len(del_resp.json()["personas"]) == 1
    finally:
        app.dependency_overrides.clear()


def test_global_personas_export_from_task_and_import_back(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("TRANSLIP_GLOBAL_PERSONAS_DIR", str(tmp_path / "global"))
    client, _ = _bootstrap(tmp_path, "global-export.db")
    try:
        # Create persona in task
        created = client.post(
            f"/api/tasks/{TASK_ID}/speaker-review/personas",
            json={"name": "旁白老王", "role": "narrator", "gender": "male"},
        ).json()["persona"]
        assert created["name"] == "旁白老王"

        # Export to global library
        exp = client.post(
            f"/api/tasks/{TASK_ID}/speaker-review/global-personas/export-from-task",
            json={"overwrite": True},
        )
        assert exp.status_code == 200, exp.text
        assert "旁白老王" in exp.json()["exported"]

        # Confirm it lives in the global library
        listed = client.get("/api/global-personas").json()
        assert any(p["name"] == "旁白老王" for p in listed["personas"])
        gid = next(p["id"] for p in listed["personas"] if p["name"] == "旁白老王")

        # Delete the task-local persona then import back from global
        client.delete(
            f"/api/tasks/{TASK_ID}/speaker-review/personas/{created['id']}"
        )
        task_personas_before = client.get(
            f"/api/tasks/{TASK_ID}/speaker-review/personas"
        ).json()["items"]
        assert all(p["name"] != "旁白老王" for p in task_personas_before)

        imp = client.post(
            f"/api/tasks/{TASK_ID}/speaker-review/personas/import-from-global",
            json={"persona_ids": [gid], "bindings_by_id": {gid: ["SPEAKER_00"]}},
        )
        assert imp.status_code == 200, imp.text
        body = imp.json()
        assert body["ok"] is True
        assert len(body["imported"]) == 1
        assert body["imported"][0]["name"] == "旁白老王"
        assert "SPEAKER_00" in body["imported"][0]["bindings"]
        assert body["conflicts"] == []
    finally:
        app.dependency_overrides.clear()


def test_global_personas_import_conflict_is_reported(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("TRANSLIP_GLOBAL_PERSONAS_DIR", str(tmp_path / "global"))
    client, _ = _bootstrap(tmp_path, "global-conflict.db")
    try:
        # Put 1 persona in global library
        client.post(
            "/api/global-personas/import",
            json={
                "personas": [{"id": "g-1", "name": "小明"}],
            },
        )
        # Create a persona of the same name in the task
        client.post(
            f"/api/tasks/{TASK_ID}/speaker-review/personas",
            json={"name": "小明"},
        )
        imp = client.post(
            f"/api/tasks/{TASK_ID}/speaker-review/personas/import-from-global",
            json={"persona_ids": ["g-1"]},
        )
        assert imp.status_code == 200, imp.text
        body = imp.json()
        assert body["imported"] == []
        assert len(body["conflicts"]) == 1
        assert body["conflicts"][0]["name"] == "小明"
    finally:
        app.dependency_overrides.clear()


def test_global_personas_smart_match(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("TRANSLIP_GLOBAL_PERSONAS_DIR", str(tmp_path / "global"))
    client, _ = _bootstrap(tmp_path, "global-match.db")
    try:
        client.post(
            "/api/global-personas/import",
            json={
                "personas": [
                    {"id": "g-narr", "name": "旁白", "role": "narrator", "gender": "male"},
                    {"id": "g-fem", "name": "女主", "role": "protagonist", "gender": "female"},
                ]
            },
        )
        resp = client.post(
            f"/api/tasks/{TASK_ID}/speaker-review/personas/suggest-from-global",
            json={
                "speakers": [
                    {"speaker_label": "SPEAKER_00", "role": "narrator", "gender": "male"},
                    {"speaker_label": "SPEAKER_01", "role": "protagonist", "gender": "female"},
                    {"speaker_label": "SPEAKER_02"},
                ]
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["ok"] is True
        matches_by_label = {m["speaker_label"]: m for m in body["matches"]}
        assert matches_by_label["SPEAKER_00"]["candidates"][0]["name"] == "旁白"
        assert matches_by_label["SPEAKER_00"]["candidates"][0]["score"] >= 0.9
        assert matches_by_label["SPEAKER_01"]["candidates"][0]["name"] == "女主"
        assert matches_by_label["SPEAKER_02"]["candidates"] == []
    finally:
        app.dependency_overrides.clear()
