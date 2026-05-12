"""Tests for TMDb integration routes."""

import json
import os

import pytest
from fastapi.testclient import TestClient

from translip.server.app import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    """Isolate tests to tmp_path."""
    monkeypatch.delenv("TMDB_API_KEY", raising=False)
    monkeypatch.delenv("TMDB_BEARER_TOKEN", raising=False)
    monkeypatch.setenv("TRANSLIP_GLOBAL_PERSONAS_DIR", str(tmp_path))
    monkeypatch.setenv("TRANSLIP_WORKS_PATH", str(tmp_path / "works.json"))
    config_dir = tmp_path / ".translip"
    config_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("TRANSLIP_CONFIG_DIR", str(config_dir))
    config_path = config_dir / "config.json"

    from translip.server.routes import config as config_module
    from translip.speaker_review.works_providers import tmdb as tmdb_module

    monkeypatch.setattr(config_module, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(config_module, "CONFIG_PATH", config_path)
    monkeypatch.setattr(tmdb_module, "TRANSLIP_CONFIG_DIR", config_dir)
    monkeypatch.setattr(tmdb_module, "CONFIG_PATH", config_path)
    monkeypatch.setattr(tmdb_module, "POSTER_CACHE_DIR", config_dir / "posters")
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

    def test_tmdb_create_work_imports_cast_into_global_personas(self, monkeypatch):
        """Creating a work from TMDb should also import its cast as characters."""

        class FakeConfig:
            def has_credentials(self):
                return True

        class FakeProvider:
            config = FakeConfig()

            def get_details(self, tmdb_id, media_type):
                assert tmdb_id == 27205
                assert media_type == "movie"
                return {
                    "tmdb_id": 27205,
                    "type": "movie",
                    "media_type": "movie",
                    "title": "盗梦空间",
                    "original_title": "Inception",
                    "year": 2010,
                    "overview": "A thief who steals corporate secrets through dream-sharing technology.",
                    "genres": ["动作", "科幻"],
                    "poster_path": "/poster.jpg",
                    "cast": [
                        {
                            "id": 6193,
                            "actor_name": "Leonardo DiCaprio",
                            "character_name": "道姆·柯布",
                            "profile_path": "/leo.jpg",
                            "order": 0,
                        },
                        {
                            "id": 24045,
                            "actor_name": "Joseph Gordon-Levitt",
                            "character_name": "亚瑟",
                            "profile_path": "/jgl.jpg",
                            "order": 1,
                        },
                    ],
                }

            def get_poster_url(self, poster_path, size="w342"):
                return f"https://image.tmdb.test/{size}{poster_path}" if poster_path else ""

            def tmdb_to_work(self, tmdb_data):
                return {
                    "title": tmdb_data["title"],
                    "type": "movie",
                    "year": tmdb_data["year"],
                    "aliases": [tmdb_data["original_title"]],
                    "external_refs": {
                        "tmdb_id": tmdb_data["tmdb_id"],
                        "tmdb_media_type": tmdb_data["media_type"],
                    },
                    "metadata": {
                        "poster_url": self.get_poster_url(tmdb_data["poster_path"]),
                        "overview": tmdb_data["overview"],
                        "genres": tmdb_data["genres"],
                        "source": "tmdb",
                    },
                    "cast_snapshot": [
                        {
                            "external_person_id": f"tmdb:{member['id']}",
                            "actor_name": member["actor_name"],
                            "character_name": member["character_name"],
                            "profile_url": self.get_poster_url(member["profile_path"]),
                            "order": member["order"],
                            "source": "tmdb",
                        }
                        for member in tmdb_data["cast"]
                    ],
                    "external_source": "tmdb",
                }

        from translip.speaker_review.works_providers import tmdb as tmdb_module

        monkeypatch.setattr(tmdb_module, "get_tmdb_provider", lambda: FakeProvider())

        response = client.post(
            "/api/works/from-tmdb",
            json={"tmdb_id": 27205, "media_type": "movie"},
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["ok"] is True
        assert [item["name"] for item in data["imported_cast"]] == ["道姆·柯布", "亚瑟"]
        assert data["imported_cast"][0]["avatar_url"] == "https://image.tmdb.test/w342/leo.jpg"

        work_id = data["work"]["id"]
        personas = client.get("/api/global-personas").json()["personas"]
        assert len(personas) == 2
        assert {p["name"] for p in personas} == {"道姆·柯布", "亚瑟"}
        assert all(p["work_id"] == work_id for p in personas)
        assert any(
            p["name"] == "道姆·柯布"
            and p["actor_name"] == "Leonardo DiCaprio"
            and p["external_refs"]["tmdb_person_id"] == "6193"
            and p["avatar_url"] == "https://image.tmdb.test/w342/leo.jpg"
            for p in personas
        )

        works = client.get("/api/works").json()["works"]
        imported_work = next(w for w in works if w["id"] == work_id)
        assert imported_work["persona_count"] == 2

    def test_config_tmdb_endpoints(self):
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
        from translip.server.routes import config as config_module

        config_path = config_module.CONFIG_PATH
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
