from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from translip.server.app import app
from translip.server.database import get_session
from translip.server.models import Task


@pytest.fixture
def isolated_env(tmp_path: Path, monkeypatch):
    """Redirect the global personas / works directory to a tmp path."""
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("TRANSLIP_GLOBAL_PERSONAS_DIR", str(home))
    yield home


def test_list_works_empty_initially(isolated_env: Path) -> None:
    client = TestClient(app)
    resp = client.get("/api/works")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["works"] == []
    assert body["unassigned_count"] == 0
    assert body["path"].endswith("works.json")


def test_create_and_list_work(isolated_env: Path) -> None:
    client = TestClient(app)
    resp = client.post(
        "/api/works",
        json={
            "title": "老友记",
            "type": "tv",
            "year": 1994,
            "aliases": ["Friends", "六人行"],
            "cover_emoji": "☕️",
        },
    )
    assert resp.status_code == 200, resp.text
    work = resp.json()["work"]
    assert work["title"] == "老友记"
    assert work["type"] == "tv"
    assert "Friends" in work["aliases"]
    assert work["id"].startswith("work_")

    listing = client.get("/api/works").json()
    assert len(listing["works"]) == 1
    assert listing["works"][0]["persona_count"] == 0


def test_create_duplicate_title_rejected(isolated_env: Path) -> None:
    client = TestClient(app)
    client.post("/api/works", json={"title": "老友记", "type": "tv"})
    dup = client.post("/api/works", json={"title": "老友记", "type": "tv"})
    assert dup.status_code == 400


def test_update_work(isolated_env: Path) -> None:
    client = TestClient(app)
    wid = client.post("/api/works", json={"title": "老友记", "type": "tv"}).json()["work"]["id"]
    resp = client.patch(
        f"/api/works/{wid}",
        json={"title": "Friends", "aliases": ["老友记"], "note": "US sitcom"},
    )
    assert resp.status_code == 200
    w = resp.json()["work"]
    assert w["title"] == "Friends"
    assert "老友记" in w["aliases"]
    assert w["note"] == "US sitcom"


def test_delete_work_default_keeps_personas_unassigned(isolated_env: Path) -> None:
    client = TestClient(app)
    wid = client.post("/api/works", json={"title": "老友记", "type": "tv"}).json()["work"]["id"]
    client.post(
        "/api/global-personas/import",
        json={
            "mode": "merge",
            "personas": [
                {"id": "p_ross", "name": "Ross", "work_id": wid},
                {"id": "p_rachel", "name": "Rachel", "work_id": wid},
            ],
        },
    )

    del_resp = client.delete(f"/api/works/{wid}")
    assert del_resp.status_code == 200
    summary = del_resp.json()
    assert summary["reassigned"] == 2
    assert summary["deleted_personas"] == 0

    personas = client.get("/api/global-personas").json()["personas"]
    for p in personas:
        assert p.get("work_id") in (None, "")


def test_delete_work_with_reassign(isolated_env: Path) -> None:
    client = TestClient(app)
    wid_a = client.post("/api/works", json={"title": "剧A", "type": "tv"}).json()["work"]["id"]
    wid_b = client.post("/api/works", json={"title": "剧B", "type": "tv"}).json()["work"]["id"]
    client.post(
        "/api/global-personas/import",
        json={
            "mode": "merge",
            "personas": [
                {"id": "p_x", "name": "X", "work_id": wid_a},
            ],
        },
    )
    resp = client.delete(f"/api/works/{wid_a}?reassign_to={wid_b}")
    assert resp.status_code == 200
    personas = client.get("/api/global-personas").json()["personas"]
    assert any(p["id"] == "p_x" and p.get("work_id") == wid_b for p in personas)


def test_delete_work_with_cascade_removes_personas(isolated_env: Path) -> None:
    client = TestClient(app)
    wid = client.post("/api/works", json={"title": "剧C", "type": "tv"}).json()["work"]["id"]
    client.post(
        "/api/global-personas/import",
        json={
            "mode": "merge",
            "personas": [
                {"id": "p_k1", "name": "K1", "work_id": wid},
                {"id": "p_k2", "name": "K2", "work_id": wid},
                {"id": "p_free", "name": "Free"},
            ],
        },
    )
    resp = client.delete(f"/api/works/{wid}?cascade=true")
    assert resp.status_code == 200
    summary = resp.json()
    assert summary["deleted_personas"] == 2
    personas = client.get("/api/global-personas").json()["personas"]
    names = {p["name"] for p in personas}
    assert "Free" in names
    assert "K1" not in names


def test_list_personas_in_work_and_unassigned(isolated_env: Path) -> None:
    client = TestClient(app)
    wid = client.post("/api/works", json={"title": "剧D", "type": "tv"}).json()["work"]["id"]
    client.post(
        "/api/global-personas/import",
        json={
            "mode": "merge",
            "personas": [
                {"id": "p_in", "name": "In", "work_id": wid},
                {"id": "p_out", "name": "Out"},
            ],
        },
    )
    in_work = client.get(f"/api/works/{wid}/personas").json()["personas"]
    unassigned = client.get("/api/works/__unassigned__/personas").json()["personas"]
    assert {p["id"] for p in in_work} == {"p_in"}
    assert {p["id"] for p in unassigned} == {"p_out"}


def test_move_personas_between_works(isolated_env: Path) -> None:
    client = TestClient(app)
    wid_a = client.post("/api/works", json={"title": "剧E", "type": "tv"}).json()["work"]["id"]
    wid_b = client.post("/api/works", json={"title": "剧F", "type": "tv"}).json()["work"]["id"]
    client.post(
        "/api/global-personas/import",
        json={
            "mode": "merge",
            "personas": [{"id": "p_mv", "name": "Mover", "work_id": wid_a}],
        },
    )
    resp = client.post(
        f"/api/works/{wid_b}/personas/move",
        json={"persona_ids": ["p_mv"]},
    )
    assert resp.status_code == 200
    personas = client.get(f"/api/works/{wid_b}/personas").json()["personas"]
    assert any(p["id"] == "p_mv" for p in personas)


def test_work_types_builtin_and_custom(isolated_env: Path) -> None:
    client = TestClient(app)
    listing = client.get("/api/work-types").json()["types"]
    keys = [t["key"] for t in listing]
    for expected in ["tv", "movie", "anime", "documentary", "short", "variety", "audiobook", "game", "other"]:
        assert expected in keys

    resp = client.post(
        "/api/work-types",
        json={"key": "podcast", "label_zh": "播客", "label_en": "Podcast"},
    )
    assert resp.status_code == 200
    assert any(t["key"] == "podcast" for t in resp.json()["types"])

    dup = client.post(
        "/api/work-types",
        json={"key": "podcast", "label_zh": "播客2", "label_en": "Podcast2"},
    )
    assert dup.status_code == 400

    conflict = client.post(
        "/api/work-types",
        json={"key": "tv", "label_zh": "X", "label_en": "X"},
    )
    assert conflict.status_code == 400

    rm = client.delete("/api/work-types/podcast")
    assert rm.status_code == 200
    assert not any(t["key"] == "podcast" for t in rm.json()["types"])

    rm_builtin = client.delete("/api/work-types/tv")
    assert rm_builtin.status_code == 400


def test_custom_type_can_be_used_for_work(isolated_env: Path) -> None:
    client = TestClient(app)
    client.post(
        "/api/work-types",
        json={"key": "podcast", "label_zh": "播客", "label_en": "Podcast"},
    )
    resp = client.post("/api/works", json={"title": "无聊斋", "type": "podcast"})
    assert resp.status_code == 200, resp.text


def test_unknown_type_rejected(isolated_env: Path) -> None:
    client = TestClient(app)
    resp = client.post("/api/works", json={"title": "X", "type": "mystery"})
    assert resp.status_code == 400


def test_bind_task_to_work(tmp_path: Path, isolated_env: Path) -> None:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'works.db'}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            Task(
                id="task-works-bind",
                name="Friends S01E01",
                status="succeeded",
                input_path=str(tmp_path / "input.mp4"),
                output_root=str(tmp_path / "output"),
                source_lang="en",
                target_lang="zh",
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
        wid = client.post("/api/works", json={"title": "Friends", "type": "tv"}).json()["work"]["id"]
        resp = client.post(
            f"/api/works/bind-task/task-works-bind",
            json={"work_id": wid, "episode_label": "S01E01"},
        )
        assert resp.status_code == 200
        data = resp.json()["task"]
        assert data["work_id"] == wid
        assert data["episode_label"] == "S01E01"

        unbind = client.post(
            f"/api/works/bind-task/task-works-bind",
            json={"work_id": None, "episode_label": None},
        )
        assert unbind.status_code == 200
        assert unbind.json()["task"]["work_id"] is None
    finally:
        app.dependency_overrides.clear()


def test_infer_and_auto_bind_task(tmp_path: Path, isolated_env: Path) -> None:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'works-infer.db'}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            Task(
                id="task-infer",
                name="dub-en-zh",
                status="succeeded",
                input_path=str(tmp_path / "Friends.S02E05.final.mkv"),
                output_root=str(tmp_path / "output"),
                source_lang="en",
                target_lang="zh",
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
        client.post("/api/works", json={"title": "Friends", "type": "tv"})

        # infer
        r = client.post("/api/works/infer-from-task/task-infer")
        assert r.status_code == 200
        cands = r.json()["candidates"]
        assert cands and cands[0]["score"] >= 0.85
        assert cands[0]["episode_label"] == "S02E05"

        # auto-bind hits
        r = client.post("/api/works/auto-bind-task/task-infer")
        assert r.status_code == 200
        assert r.json()["bound"] is True
        assert r.json()["episode_label"] == "S02E05"
    finally:
        app.dependency_overrides.clear()


def test_auto_bind_skips_when_no_high_confidence(tmp_path: Path, isolated_env: Path) -> None:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'works-infer2.db'}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            Task(
                id="task-low",
                name="random-file",
                status="succeeded",
                input_path=str(tmp_path / "random.mp4"),
                output_root=str(tmp_path / "output"),
                source_lang="en",
                target_lang="zh",
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
        r = client.post("/api/works/auto-bind-task/task-low")
        assert r.status_code == 200
        assert r.json()["bound"] is False
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Phase 1 Batch A: external-source fields (TMDb / Wikidata interop substrate)
# ---------------------------------------------------------------------------


def test_create_work_persists_external_fields(isolated_env: Path) -> None:
    """External-source fields (poster, synopsis, cast snapshot, refs) must be
    accepted at creation time and round-trip through GET /api/works."""
    client = TestClient(app)
    payload = {
        "title": "老友记 (S01)",
        "type": "tv",
        "year": 1994,
        "external_refs": {
            "tmdb_id": 1668,
            "imdb_id": "tt0108778",
            "tmdb_media_type": "tv",
        },
        "poster_path": "assets/works/work_x/poster.jpg",
        "backdrop_path": "assets/works/work_x/backdrop.jpg",
        "synopsis": "六个住在纽约的好朋友的日常故事。",
        "synopsis_lang": "zh",
        "origin_country": ["US"],
        "original_title": "Friends",
        "external_source": "tmdb",
        "external_synced_at": "2026-05-11T10:00:00",
        "cast_snapshot": [
            {
                "external_person_id": "tmdb:1100",
                "actor": "Jennifer Aniston",
                "actor_aliases": ["詹妮弗·安妮斯顿"],
                "character": "Rachel Green",
                "character_aliases": [],
                "order": 0,
                "profile_path": "/abc.jpg",
                "gender": "female",
            }
        ],
    }
    resp = client.post("/api/works", json=payload)
    assert resp.status_code == 200, resp.text
    work = resp.json()["work"]
    assert work["external_refs"]["tmdb_id"] == 1668
    assert work["external_refs"]["imdb_id"] == "tt0108778"
    metadata = work.get("metadata") or {}
    assert metadata.get("poster_url") == "assets/works/work_x/poster.jpg"
    assert metadata.get("backdrop_url") == "assets/works/work_x/backdrop.jpg"
    assert metadata.get("overview", "").startswith("六个")
    assert metadata.get("overview_lang") == "zh"
    assert metadata.get("original_title") == "Friends"
    assert metadata.get("origin_country") == ["US"]
    assert metadata.get("source") == "tmdb"
    assert len(work["cast_snapshot"]) == 1
    cast0 = work["cast_snapshot"][0]
    assert cast0["actor_name"] == "Jennifer Aniston"
    assert cast0["character_name"] == "Rachel Green"
    assert cast0["profile_url"] == "/abc.jpg"

    list_resp = client.get("/api/works")
    fetched = next(w for w in list_resp.json()["works"] if w["id"] == work["id"])
    assert (fetched.get("metadata") or {}).get("overview", "").startswith("六个")


def test_patch_work_merges_external_fields_without_clobbering_user_fields(
    isolated_env: Path,
) -> None:
    """PATCH should merge external fields and leave manually-edited fields intact."""
    client = TestClient(app)
    create = client.post(
        "/api/works",
        json={"title": "测试作品 A", "type": "movie", "note": "用户备注不应被覆盖"},
    )
    assert create.status_code == 200
    work_id = create.json()["work"]["id"]

    patch = client.patch(
        f"/api/works/{work_id}",
        json={
            "external_refs": {"tmdb_id": 9999},
            "poster_path": "assets/works/x/p.jpg",
            "synopsis": "外部抓取的简介",
            "external_source": "tmdb",
        },
    )
    assert patch.status_code == 200, patch.text
    updated = patch.json()["work"]
    assert updated["note"] == "用户备注不应被覆盖"
    assert updated["external_refs"]["tmdb_id"] == 9999
    metadata = updated.get("metadata") or {}
    assert metadata.get("poster_url") == "assets/works/x/p.jpg"
    assert metadata.get("overview") == "外部抓取的简介"
    assert metadata.get("source") == "tmdb"


def test_create_work_without_external_fields_is_backward_compatible(
    isolated_env: Path,
) -> None:
    """Legacy clients that omit external_* fields must still work and produce
    a clean record (no None placeholders leaking into the JSON)."""
    client = TestClient(app)
    resp = client.post("/api/works", json={"title": "纯手填作品", "type": "movie"})
    assert resp.status_code == 200
    work = resp.json()["work"]
    for key in (
        "metadata",
        "cast_snapshot",
        "external_refs",
    ):
        assert key not in work or work[key] in (None, [], {}), (
            f"{key}={work.get(key)}"
        )


def test_patch_work_deep_merges_metadata_and_preserves_user_edits(
    isolated_env: Path,
) -> None:
    """Canonical-shape sync: write `metadata.genres`, then a second sync that
    only carries `metadata.overview` must NOT wipe `genres`. Also verifies the
    canonical `cast_snapshot[].actor_name/character_name/profile_url` shape
    round-trips unchanged (matches existing ~/.translip/works.json layout)."""
    client = TestClient(app)
    create = client.post(
        "/api/works",
        json={
            "title": "哪吒之魔童闹海 (fixture)",
            "type": "movie",
            "external_refs": {"tmdb_id": 123, "tmdb_media_type": "movie"},
        },
    )
    assert create.status_code == 200
    work_id = create.json()["work"]["id"]

    first = client.patch(
        f"/api/works/{work_id}",
        json={
            "metadata": {
                "poster_url": "https://image.tmdb.org/t/p/w500/p1.jpg",
                "overview": "首次同步的剧情简介。",
                "genres": ["动画", "奇幻"],
                "release_date": "2025-01-29",
                "source": "tmdb",
            },
            "cast_snapshot": [
                {
                    "external_person_id": "tmdb:9001",
                    "actor_name": "吕艳婷",
                    "character_name": "哪吒",
                    "profile_url": "https://image.tmdb.org/t/p/w185/a.jpg",
                    "order": 0,
                }
            ],
        },
    )
    assert first.status_code == 200, first.text
    meta1 = first.json()["work"]["metadata"]
    assert meta1["genres"] == ["动画", "奇幻"]
    assert meta1["release_date"] == "2025-01-29"
    cast1 = first.json()["work"]["cast_snapshot"]
    assert cast1[0]["actor_name"] == "吕艳婷"
    assert cast1[0]["character_name"] == "哪吒"
    assert cast1[0]["profile_url"].endswith("/a.jpg")

    # Second sync only updates overview — genres / release_date MUST survive.
    second = client.patch(
        f"/api/works/{work_id}",
        json={"metadata": {"overview": "第二次同步改写的简介。"}},
    )
    assert second.status_code == 200, second.text
    meta2 = second.json()["work"]["metadata"]
    assert meta2["overview"] == "第二次同步改写的简介。"
    assert meta2["genres"] == ["动画", "奇幻"]  # preserved by deep-merge
    assert meta2["release_date"] == "2025-01-29"
    assert meta2["poster_url"].endswith("/p1.jpg")
