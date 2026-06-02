from __future__ import annotations

import json
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
    assert payload["vad_filter"] is True
    assert payload["vad_min_silence_duration_ms"] == 400
    assert payload["beam_size"] == 5
    assert payload["best_of"] == 5
    assert payload["temperature"] == 0.0
    assert payload["condition_on_previous_text"] is False
    assert payload["stage1_output_format"] == "mp3"
    assert payload["translation_batch_size"] == 4
    assert payload["background_gain_db"] == -8.0
    assert payload["window_ducking_db"] == -3.0
    assert payload["max_compress_ratio"] == 1.45


def test_global_config_round_trips_transcription_advanced_defaults(tmp_path, monkeypatch) -> None:
    from translip.server.routes import config as config_routes

    monkeypatch.setattr(config_routes, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config_routes, "CONFIG_PATH", tmp_path / "config.json")

    client = TestClient(app_module.app)

    update = {
        "asr_model": "medium",
        "vad_filter": False,
        "vad_min_silence_duration_ms": 650,
        "beam_size": 3,
        "best_of": 2,
        "temperature": 0.2,
        "condition_on_previous_text": True,
        "stage1_output_format": "wav",
        "top_k": 4,
        "translation_backend": "deepseek",
        "translation_batch_size": 8,
        "condense_mode": "smart",
        "deepseek_model": "deepseek-v4-pro",
        "tts_backend": "qwen3tts",
        "dubbing_workers": 2,
        "dubbing_quality_check": "duration-only",
        "dub_repair_enabled": True,
        "dub_repair_backend": ["moss-tts-nano-onnx", "qwen3tts"],
        "dub_repair_max_items": 6,
        "dub_repair_attempts_per_item": 2,
        "dub_repair_include_risk": True,
        "fit_policy": "high_quality",
        "fit_backend": "rubberband",
        "mix_profile": "enhanced",
        "ducking_mode": "sidechain",
        "background_gain_db": -10.0,
        "window_ducking_db": -4.0,
        "max_compress_ratio": 1.35,
        "subtitle_mode": "bilingual",
        "subtitle_render_source": "asr",
    }

    response = client.put("/api/config/global", json=update)

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    for key, value in update.items():
        assert payload["config"][key] == value

    saved = client.get("/api/config/global")

    assert saved.status_code == 200
    saved_payload = saved.json()
    for key, value in update.items():
        assert saved_payload[key] == value


def test_global_config_can_clear_optional_advanced_defaults(tmp_path, monkeypatch) -> None:
    from translip.server.routes import config as config_routes

    monkeypatch.setattr(config_routes, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config_routes, "CONFIG_PATH", tmp_path / "config.json")

    client = TestClient(app_module.app)

    set_response = client.put(
        "/api/config/global",
        json={
            "deepseek_model": "deepseek-v4-pro",
            "dubbing_workers": 2,
        },
    )
    assert set_response.status_code == 200

    clear_response = client.put(
        "/api/config/global",
        json={
            "deepseek_model": None,
            "dubbing_workers": None,
        },
    )

    assert clear_response.status_code == 200
    payload = clear_response.json()
    assert payload["config"]["deepseek_model"] is None
    assert payload["config"]["dubbing_workers"] is None

    raw = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert "deepseek_model" not in raw["global"]
    assert "dubbing_workers" not in raw["global"]
