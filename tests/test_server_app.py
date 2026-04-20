from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from translip.server import app as app_module


def test_frontend_dist_path_points_to_repo_frontend_dist() -> None:
    expected = Path(__file__).resolve().parents[1] / "frontend" / "dist"

    assert app_module._FRONTEND_DIST == expected
    assert app_module._FRONTEND_DIST.exists()


def test_frontend_spa_fallback_serves_index_html_for_task_routes() -> None:
    client = TestClient(app_module.app)

    response = client.get("/tasks/smoke-workflow-120")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "<!doctype html>" in response.text.lower()


def test_config_defaults_run_full_pipeline_to_task_g() -> None:
    client = TestClient(app_module.app)

    response = client.get("/api/config/defaults")

    assert response.status_code == 200
    payload = response.json()
    assert payload["run_to_stage"] == "task-g"
    assert payload["tts_backend"] == "moss-tts-nano-onnx"
