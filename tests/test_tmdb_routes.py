"""Tests for TMDb integration routes."""

from pathlib import Path
import json
import os

import pytest
from fastapi.testclient import TestClient

from src.translip.server.app import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    """Isolate tests to tmp_path."""
    monkeypatch.setenv("TRANSLIP_GLOBAL_PERSONAS_DIR", str(tmp_path))
    monkeypatch.setenv("TRANSLIP_WORKS_PATH", str(tmp_path / "works.json"))
    config_dir = tmp_path / ".translip"
    config_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("TRANSLIP_CONFIG_DIR", str(config_dir))
    yield
    # Cleanup


class TestTMDbRoutes:
    """Test TMDb API endpoints."""

    def test_tmdb_search_without_key(self):
        """Test search returns error when no API key configured."""
        response = client.get("/api/works/tmdb/search", params={"q": "test"})
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] == False
        assert "TMDb API key not configured" in data["error"]
        assert data["results"] == []

    def test_tmdb_get_details_without_key(self):
        """Test get details returns error when no API key configured."""
        response = client.get("/api/works/tmdb/123", params={"media_type": "movie"})
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] == False
        assert "TMDb API key not configured" in data["error"]

    def test_tmdb_create_work_without_key(self):
        """Test create work returns error when no API key configured."""
        response = client.post(
            "/api/works/from-tmdb",
            json={"tmdb_id": 123, "media_type": "movie"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] == False
        assert "TMDb API key not configured" in data["error"]

    def test_config_tmdb_endpoints(self, tmp_path):
        """Test TMDb config get/save endpoints."""
        # Get initial config (no config file exists)
        response = client.get("/api/config/tmdb")
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] == True
        assert data["api_key_v3_set"] == False
        assert data["api_key_v4_set"] == False
        assert data["default_language"] == "zh-CN"

        # Save config
        response = client.post(
            "/api/config/tmdb",
            json={
                "api_key_v3": "test-v3-key",
                "api_key_v4": "test-v4-key",
                "default_language": "en-US"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] == True
        assert data["message"] == "TMDb configuration saved"

        # Verify config file was created
        config_path = Path.home() / ".translip" / "config.json"
        assert config_path.exists()
        
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        assert config["tmdb"]["api_key_v3"] == "test-v3-key"
        assert config["tmdb"]["api_key_v4"] == "test-v4-key"
        assert config["tmdb"]["default_language"] == "en-US"

        # Get config again
        response = client.get("/api/config/tmdb")
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] == True
        assert data["api_key_v3_set"] == True
        assert data["api_key_v4_set"] == True
        assert data["default_language"] == "en-US"

        # Cleanup
        if config_path.exists():
            os.remove(config_path)
