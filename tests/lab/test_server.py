"""Lab dashboard server endpoints (FastAPI TestClient, no ML)."""
from __future__ import annotations

import json

from fastapi.testclient import TestClient

from translip_lab.server.app import app


def _client(monkeypatch, tmp_path):
    monkeypatch.setenv("TRANSLIP_LAB_HOME", str(tmp_path))
    return TestClient(app)


def test_index_served(monkeypatch, tmp_path):
    r = _client(monkeypatch, tmp_path).get("/")
    assert r.status_code == 200 and "translip-lab" in r.text


def test_scenarios_endpoint(monkeypatch, tmp_path):
    data = _client(monkeypatch, tmp_path).get("/api/lab/scenarios").json()
    names = {d["name"] for d in data}
    assert {"asr", "diarization", "ocr-detect", "subtitle-erase"} <= names


def test_datasets_endpoint(monkeypatch, tmp_path):
    data = _client(monkeypatch, tmp_path).get("/api/lab/datasets").json()
    names = {d["name"] for d in data}
    assert "synthetic-subtitle" in names and "alimeeting" in names


def test_suites_endpoint(monkeypatch, tmp_path):
    data = _client(monkeypatch, tmp_path).get("/api/lab/suites").json()
    assert "asr-diar-meeting" in data and "ocr-erase-synthetic" in data


def test_runs_listing_and_detail(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    assert client.get("/api/lab/runs").json() == []
    assert client.get("/api/lab/runs/does-not-exist").status_code == 404

    run_dir = tmp_path / "runs" / "r1"
    run_dir.mkdir(parents=True)
    (run_dir / "run-manifest.json").write_text(json.dumps({
        "run_id": "r1", "suite": "s", "dataset": "d", "scenarios": ["asr"],
        "aggregates": {"asr": {"primary_metric": "cer", "mean": 0.2}}, "results": [],
    }), encoding="utf-8")
    listing = client.get("/api/lab/runs").json()
    assert listing and listing[0]["run_id"] == "r1"
    assert client.get("/api/lab/runs/r1").json()["aggregates"]["asr"]["mean"] == 0.2


def test_compare_endpoint(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    for rid, mean in (("a", 0.2), ("b", 0.3)):
        d = tmp_path / "runs" / rid
        d.mkdir(parents=True)
        (d / "run-manifest.json").write_text(json.dumps({
            "run_id": rid, "aggregates": {"asr": {"primary_metric": "cer", "higher_is_better": False, "mean": mean}},
        }), encoding="utf-8")
    cmp = client.get("/api/lab/compare?baseline=a&candidate=b").json()
    assert cmp["regressions"] == ["asr"]
