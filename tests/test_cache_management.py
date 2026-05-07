"""Tests for the cache management endpoints and helpers."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from translip.server import cache_manager
from translip.server.routes import system as system_routes


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def isolated_cache_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolate persisted user-config and cache root for tests."""
    user_config = tmp_path / "user-config" / "settings.json"
    monkeypatch.delenv("TRANSLIP_CACHE_DIR", raising=False)
    cache_manager.set_user_config_path(user_config)

    cache_root = tmp_path / "cache"
    cache_root.mkdir()
    cache_manager.update_user_setting("cache_dir", str(cache_root))
    cache_manager.apply_active_cache_root()
    cache_manager.migration_manager.reset()
    # Reset the per-process breakdown short-cache so each test sees fresh data.
    system_routes._invalidate_breakdown_cache()

    yield cache_root

    cache_manager.set_user_config_path(
        Path(os.environ.get("HOME", "/tmp")) / ".config" / "translip" / "settings.json"
    )
    system_routes._invalidate_breakdown_cache()


@pytest.fixture
def client() -> TestClient:
    # Build a minimal FastAPI app with only the system router so we
    # don't trigger heavy DB / model imports.
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(system_routes.router)
    return TestClient(app)


# ---------------------------------------------------------------------------
# Persistence & resolution
# ---------------------------------------------------------------------------


def test_user_config_round_trip(tmp_path: Path) -> None:
    user_config = tmp_path / "user.json"
    cache_manager.set_user_config_path(user_config)
    cache_manager.update_user_setting("cache_dir", "/tmp/foo")
    assert cache_manager.read_user_setting("cache_dir") == "/tmp/foo"

    data = json.loads(user_config.read_text(encoding="utf-8"))
    assert data == {"cache_dir": "/tmp/foo"}

    cache_manager.update_user_setting("cache_dir", None)
    assert cache_manager.read_user_setting("cache_dir") is None


def test_resolve_active_cache_root_priority(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cache_manager.set_user_config_path(tmp_path / "settings.json")
    monkeypatch.delenv("TRANSLIP_CACHE_DIR", raising=False)

    # Defaults to home/.cache/translip
    assert cache_manager.resolve_active_cache_root() == cache_manager.default_cache_root()

    cache_manager.update_user_setting("cache_dir", str(tmp_path / "stored"))
    assert cache_manager.resolve_active_cache_root() == (tmp_path / "stored")

    monkeypatch.setenv("TRANSLIP_CACHE_DIR", str(tmp_path / "from-env"))
    assert cache_manager.resolve_active_cache_root() == (tmp_path / "from-env")


# ---------------------------------------------------------------------------
# Breakdown & cleanup
# ---------------------------------------------------------------------------


def _populate(cache_root: Path) -> None:
    cdx = cache_root / "models" / "cdx23"
    cdx.mkdir(parents=True)
    (cdx / "weights.th").write_bytes(b"x" * 100)
    (cache_root / "speechbrain" / "spkrec-ecapa-voxceleb").mkdir(parents=True)
    (cache_root / "speechbrain" / "spkrec-ecapa-voxceleb" / "model.pt").write_bytes(b"y" * 50)
    (cache_root / "garbage.tmp").write_bytes(b"z" * 30)
    pipeline_dir = cache_root / "output-pipeline" / "task-001"
    pipeline_dir.mkdir(parents=True)
    (pipeline_dir / "final.mp4").write_bytes(b"p" * 250)


def test_compute_breakdown_includes_known_groups(isolated_cache_env: Path) -> None:
    cache_root = isolated_cache_env
    _populate(cache_root)

    breakdown = cache_manager.compute_breakdown(
        cache_root=cache_root, huggingface_cache_root=cache_root / ".__no_hf__"
    )
    keys = {item["key"] for item in breakdown["items"]}
    assert {"cdx23", "speechbrain_ecapa", "temp", "hf_hub", "pipeline_outputs"} <= keys
    assert breakdown["cache_dir"] == str(cache_root)

    by_key = {item["key"]: item for item in breakdown["items"]}
    assert by_key["cdx23"]["bytes"] >= 100
    assert by_key["cdx23"]["present"] is True
    assert by_key["speechbrain_ecapa"]["present"] is True
    assert by_key["temp"]["bytes"] >= 30
    assert by_key["pipeline_outputs"]["present"] is True
    assert by_key["pipeline_outputs"]["bytes"] >= 250
    assert by_key["pipeline_outputs"]["paths"] == [str(cache_root / "output-pipeline")]


def test_cleanup_group_removes_paths(isolated_cache_env: Path) -> None:
    cache_root = isolated_cache_env
    _populate(cache_root)

    freed = cache_manager.cleanup_group(
        "cdx23", cache_root=cache_root, hf_root=cache_root / ".__no_hf__"
    )
    assert freed >= 100
    assert not (cache_root / "models" / "cdx23").exists()


def test_cleanup_group_unknown_key_raises(isolated_cache_env: Path) -> None:
    with pytest.raises(cache_manager.CachePathError):
        cache_manager.cleanup_group("does_not_exist")


def test_cleanup_groups_aggregates_results(isolated_cache_env: Path) -> None:
    cache_root = isolated_cache_env
    _populate(cache_root)

    result = cache_manager.cleanup_groups(["cdx23", "temp", "bogus"])
    detail_by_key = {d["key"]: d for d in result["details"]}
    assert "error" not in detail_by_key["cdx23"]
    assert detail_by_key["bogus"]["error"].startswith("unknown_group")
    assert result["freed_bytes"] >= 130


# ---------------------------------------------------------------------------
# Path validation & directory switching
# ---------------------------------------------------------------------------


def test_validate_target_path_rejects_root() -> None:
    with pytest.raises(cache_manager.CachePathError):
        cache_manager.validate_target_path(Path("/"))


def test_validate_target_path_rejects_system_prefix(tmp_path: Path) -> None:
    with pytest.raises(cache_manager.CachePathError):
        cache_manager.validate_target_path(Path("/etc/translip-cache"))


def test_validate_target_path_accepts_tmp(tmp_path: Path) -> None:
    target = tmp_path / "cache-new"
    resolved = cache_manager.validate_target_path(target)
    assert resolved.parent == tmp_path.resolve()


def test_set_cache_dir_persists_setting(isolated_cache_env: Path, tmp_path: Path) -> None:
    new_dir = tmp_path / "switched"
    path = cache_manager.set_cache_dir(str(new_dir))
    assert path.exists()
    assert cache_manager.read_user_setting("cache_dir") == str(new_dir.resolve())
    assert cache_manager.resolve_active_cache_root() == new_dir.resolve()


def test_reset_cache_dir_to_default(isolated_cache_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TRANSLIP_CACHE_DIR", raising=False)
    cache_manager.update_user_setting("cache_dir", str(isolated_cache_env))
    new_default = cache_manager.reset_cache_dir_to_default()
    assert cache_manager.read_user_setting("cache_dir") is None
    assert new_default == cache_manager.default_cache_root()


# ---------------------------------------------------------------------------
# Migration task lifecycle
# ---------------------------------------------------------------------------


def test_migration_copy_succeeds_synchronously(isolated_cache_env: Path, tmp_path: Path) -> None:
    src = isolated_cache_env
    (src / "a").mkdir()
    (src / "a" / "f1.bin").write_bytes(b"a" * 4096)
    (src / "a" / "f2.bin").write_bytes(b"b" * 2048)
    dst = tmp_path / "dst"

    task = cache_manager.migration_manager.start(
        target=str(dst),
        mode="copy",
        switch_after=False,
        run_in_thread=False,
    )
    assert task.state == "succeeded"
    assert (dst / "a" / "f1.bin").read_bytes() == b"a" * 4096
    assert (dst / "a" / "f2.bin").read_bytes() == b"b" * 2048
    # Source preserved in copy mode
    assert (src / "a" / "f1.bin").exists()
    assert task.copied_bytes == 4096 + 2048


def test_migration_move_switches_active_cache_dir(isolated_cache_env: Path, tmp_path: Path) -> None:
    src = isolated_cache_env
    (src / "data.bin").write_bytes(b"hello")
    dst = tmp_path / "moved"

    task = cache_manager.migration_manager.start(
        target=str(dst), mode="move", switch_after=True, run_in_thread=False
    )
    assert task.state == "succeeded"
    assert not (src / "data.bin").exists()
    assert (dst / "data.bin").read_bytes() == b"hello"
    assert cache_manager.resolve_active_cache_root() == dst.resolve()


def test_migration_target_equals_source_rejected(isolated_cache_env: Path) -> None:
    with pytest.raises(cache_manager.CachePathError):
        cache_manager.migration_manager.start(
            target=str(isolated_cache_env), mode="copy", run_in_thread=False
        )


def test_migration_can_be_cancelled(isolated_cache_env: Path, tmp_path: Path) -> None:
    src = isolated_cache_env
    # Make the data large enough so we can cancel mid-flight
    payload = b"x" * (1024 * 1024)
    for i in range(8):
        (src / f"chunk-{i}.bin").write_bytes(payload)
    dst = tmp_path / "cancel-dst"

    cache_manager.migration_manager.chunk_size = 64 * 1024  # slow it down
    try:
        task = cache_manager.migration_manager.start(
            target=str(dst), mode="copy", switch_after=False, run_in_thread=True
        )
        time.sleep(0.05)
        cache_manager.migration_manager.cancel(task.task_id)
        if task.thread is not None:
            task.thread.join(timeout=10)
        assert task.state in {"cancelled", "succeeded"}
        if task.state == "cancelled":
            # Rolled-back: target should be empty (or partially scrubbed)
            remaining = list(dst.rglob("*"))
            files = [p for p in remaining if p.is_file()]
            assert files == []
    finally:
        cache_manager.migration_manager.chunk_size = 1024 * 1024


# ---------------------------------------------------------------------------
# HTTP-level smoke tests
# ---------------------------------------------------------------------------


def test_breakdown_endpoint(client: TestClient, isolated_cache_env: Path) -> None:
    _populate(isolated_cache_env)
    resp = client.get("/api/system/cache/breakdown")
    assert resp.status_code == 200
    data = resp.json()
    assert data["cache_dir"] == str(isolated_cache_env)
    keys = {item["key"] for item in data["items"]}
    assert "cdx23" in keys


def test_set_dir_endpoint_validates(client: TestClient, isolated_cache_env: Path) -> None:
    resp = client.post("/api/system/cache/set-dir", json={"target": "/etc/anything"})
    assert resp.status_code == 400


def test_set_dir_endpoint_accepts_valid(client: TestClient, isolated_cache_env: Path, tmp_path: Path) -> None:
    target = tmp_path / "ui-switch"
    resp = client.post(
        "/api/system/cache/set-dir",
        json={"target": str(target), "create_if_missing": True},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert Path(body["cache_dir"]) == target.resolve()


def test_delete_item_endpoint(client: TestClient, isolated_cache_env: Path) -> None:
    _populate(isolated_cache_env)
    resp = client.delete("/api/system/cache/item", params={"key": "cdx23"})
    assert resp.status_code == 200
    assert resp.json()["freed_bytes"] >= 100


def test_cleanup_endpoint_rejects_empty(client: TestClient, isolated_cache_env: Path) -> None:
    resp = client.post("/api/system/cache/cleanup", json={"keys": []})
    assert resp.status_code == 400


def test_cleanup_endpoint(client: TestClient, isolated_cache_env: Path) -> None:
    _populate(isolated_cache_env)
    resp = client.post(
        "/api/system/cache/cleanup", json={"keys": ["cdx23", "temp"]}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert {d["key"] for d in body["details"]} == {"cdx23", "temp"}


def test_migrate_endpoint_lifecycle(
    client: TestClient, isolated_cache_env: Path, tmp_path: Path
) -> None:
    (isolated_cache_env / "tiny.bin").write_bytes(b"data")
    target = tmp_path / "migrated"

    cache_manager.migration_manager.chunk_size = 64
    try:
        resp = client.post(
            "/api/system/cache/migrate",
            json={"target": str(target), "mode": "copy", "switch_after": False},
        )
        assert resp.status_code == 200, resp.text
        task_id = resp.json()["task_id"]

        # Poll
        deadline = time.time() + 5
        state = "pending"
        while time.time() < deadline:
            poll = client.get(f"/api/system/cache/migrate/{task_id}")
            assert poll.status_code == 200
            state = poll.json()["status"]
            if state in {"succeeded", "failed", "cancelled"}:
                break
            time.sleep(0.05)
        assert state == "succeeded"
        assert (target / "tiny.bin").read_bytes() == b"data"
    finally:
        cache_manager.migration_manager.chunk_size = 1024 * 1024


def test_migrate_unknown_task_returns_404(client: TestClient, isolated_cache_env: Path) -> None:
    resp = client.get("/api/system/cache/migrate/does-not-exist")
    assert resp.status_code == 404


def test_migrate_cancel_unknown_task_returns_404(
    client: TestClient, isolated_cache_env: Path
) -> None:
    resp = client.post("/api/system/cache/migrate/missing/cancel")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Audit hardenings (new defenses)
# ---------------------------------------------------------------------------


def test_validate_target_path_rejects_empty_string() -> None:
    with pytest.raises(cache_manager.CachePathError):
        cache_manager.validate_target_path(Path(""))


def test_validate_target_path_rejects_extra_system_prefixes(tmp_path: Path) -> None:
    for forbidden in ("/opt/anywhere", "/srv/data", "/var/db/x"):
        with pytest.raises(cache_manager.CachePathError):
            cache_manager.validate_target_path(Path(forbidden))


def test_cleanup_groups_deduplicates_keys(isolated_cache_env: Path) -> None:
    _populate(isolated_cache_env)
    result = cache_manager.cleanup_groups(["cdx23", "cdx23", "temp"])
    keys_seen = [d["key"] for d in result["details"]]
    assert keys_seen == ["cdx23", "temp"]


def test_collect_temp_skips_hf_inflight(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cache_root = tmp_path / "cache"
    hf_root = tmp_path / "hf-hub"
    cache_root.mkdir()
    hf_root.mkdir()
    monkeypatch.setenv("HF_HUB_CACHE", str(hf_root))
    # Create one in-flight HF download and one normal temp file under cache_root
    (hf_root / "models--demo").mkdir()
    (hf_root / "models--demo" / "weights.bin.incomplete").write_bytes(b"d" * 100)
    (cache_root / "garbage.tmp").write_bytes(b"g" * 50)
    # Make HF a child of cache_root for the rglob path
    nested_hf = cache_root / "huggingface" / "hub"
    nested_hf.mkdir(parents=True)
    (nested_hf / "models--x" / "f.bin.incomplete").parent.mkdir(parents=True)
    (nested_hf / "models--x" / "f.bin.incomplete").write_bytes(b"x" * 30)
    monkeypatch.setenv("HF_HUB_CACHE", str(nested_hf))

    items = cache_manager._collect_temp_files(cache_root)
    paths = {str(p) for p in items}
    assert str(cache_root / "garbage.tmp") in paths
    # HF in-flight downloads must be skipped
    assert str(nested_hf / "models--x" / "f.bin.incomplete") not in paths


def test_migrate_rejects_non_empty_target(isolated_cache_env: Path, tmp_path: Path) -> None:
    dst = tmp_path / "non-empty"
    dst.mkdir()
    (dst / "leftover.txt").write_text("existing")
    with pytest.raises(cache_manager.CachePathError) as excinfo:
        cache_manager.migration_manager.start(
            target=str(dst), mode="copy", switch_after=False, run_in_thread=False
        )
    assert "target_not_empty" in str(excinfo.value)


def test_migrate_allows_non_empty_when_flag_set(isolated_cache_env: Path, tmp_path: Path) -> None:
    src = isolated_cache_env
    (src / "src.bin").write_bytes(b"hello")
    dst = tmp_path / "non-empty-allowed"
    dst.mkdir()
    (dst / "leftover.txt").write_text("preexisting")
    task = cache_manager.migration_manager.start(
        target=str(dst),
        mode="copy",
        switch_after=False,
        run_in_thread=False,
        allow_non_empty=True,
    )
    assert task.state == "succeeded"
    assert (dst / "src.bin").read_bytes() == b"hello"
    assert (dst / "leftover.txt").read_text() == "preexisting"


def test_breakdown_endpoint_short_caches(
    client: TestClient, isolated_cache_env: Path
) -> None:
    _populate(isolated_cache_env)
    r1 = client.get("/api/system/cache/breakdown")
    total1 = r1.json()["total_bytes"]
    # Add data after the first call - within TTL the cached value should still be returned.
    (isolated_cache_env / "models" / "cdx23" / "extra.th").write_bytes(b"q" * 999)
    r2 = client.get("/api/system/cache/breakdown")
    assert r2.json()["total_bytes"] == total1
    # ?refresh=true bypasses the cache.
    r3 = client.get("/api/system/cache/breakdown?refresh=true")
    assert r3.json()["total_bytes"] >= total1 + 999


def test_migration_manager_gc_finished_history(
    isolated_cache_env: Path, tmp_path: Path
) -> None:
    src = isolated_cache_env
    (src / "x.bin").write_bytes(b"abc")
    cache_manager.migration_manager._TASK_HISTORY_LIMIT = 3  # type: ignore[attr-defined]
    try:
        for i in range(6):
            target = tmp_path / f"history-{i}"
            cache_manager.migration_manager.start(
                target=str(target),
                mode="copy",
                switch_after=False,
                run_in_thread=False,
            )
        # After the GC kicks in, only the most recent <= 3 tasks should remain.
        assert len(cache_manager.migration_manager.list_tasks()) <= 3
    finally:
        cache_manager.migration_manager._TASK_HISTORY_LIMIT = 16  # type: ignore[attr-defined]
        cache_manager.migration_manager.reset()
