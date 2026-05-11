"""TMDb (The Movie Database) provider for work metadata.

Handles:
- Searching for movies/tv shows
- Fetching detailed metadata
- Downloading and caching posters
- Normalizing TMDb response to canonical work format

API keys are loaded from ~/.translip/config.json:
{
  "tmdb": {
    "api_key_v3": "...",
    "api_key_v4": "...",
    "default_language": "zh-CN"
  }
}
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional, Tuple

import requests

TRANSLIP_CONFIG_DIR = Path.home() / ".translip"
CONFIG_PATH = TRANSLIP_CONFIG_DIR / "config.json"
POSTER_CACHE_DIR = TRANSLIP_CONFIG_DIR / "posters"


class TMDbConfig:
    api_key_v3: str
    api_key_v4: str
    default_language: str

    def __init__(self):
        self._load_config()

    def _load_config(self):
        if not CONFIG_PATH.exists():
            self.api_key_v3 = os.environ.get("TMDB_API_KEY", "")
            self.api_key_v4 = os.environ.get("TMDB_BEARER_TOKEN", "")
            self.default_language = "zh-CN"
            return

        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                config = json.load(f)
            tmdb_config = config.get("tmdb", {})
            self.api_key_v3 = tmdb_config.get("api_key_v3", os.environ.get("TMDB_API_KEY", ""))
            self.api_key_v4 = tmdb_config.get("api_key_v4", os.environ.get("TMDB_BEARER_TOKEN", ""))
            self.default_language = tmdb_config.get("default_language", "zh-CN")
        except (json.JSONDecodeError, IOError):
            self.api_key_v3 = os.environ.get("TMDB_API_KEY", "")
            self.api_key_v4 = os.environ.get("TMDB_BEARER_TOKEN", "")
            self.default_language = "zh-CN"

    def has_credentials(self) -> bool:
        return bool(self.api_key_v3 or self.api_key_v4)


class TMDbProvider:
    BASE_URL_V3 = "https://api.themoviedb.org/3"
    BASE_URL_V4 = "https://api.themoviedb.org/4"
    IMAGE_BASE_URL = "https://image.tmdb.org/t/p"

    def __init__(self):
        self.config = TMDbConfig()
        self._session = requests.Session()
        POSTER_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def _get_headers(self, use_v4: bool = True) -> dict[str, str]:
        if use_v4 and self.config.api_key_v4:
            return {"Authorization": f"Bearer {self.config.api_key_v4}"}
        return {"Authorization": f"Bearer {self.config.api_key_v3}"}

    def search(self, query: str, media_type: Optional[str] = None) -> list[dict[str, Any]]:
        """Search TMDb for movies/tv shows.
        
        Args:
            query: Search term
            media_type: "movie", "tv", or None for both
        
        Returns:
            List of search results with minimal metadata
        """
        results = []
        
        if media_type in ("movie", None):
            results.extend(self._search_movies(query))
        
        if media_type in ("tv", None):
            results.extend(self._search_tv(query))
        
        results.sort(key=lambda x: x.get("popularity", 0), reverse=True)
        return results[:20]

    def _search_movies(self, query: str) -> list[dict[str, Any]]:
        url = f"{self.BASE_URL_V3}/search/movie"
        params = {
            "query": query,
            "language": self.config.default_language,
            "include_adult": False,
            "api_key": self.config.api_key_v3,
        }
        try:
            resp = self._session.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            return [self._normalize_movie_result(r) for r in data.get("results", [])]
        except Exception:
            return []

    def _search_tv(self, query: str) -> list[dict[str, Any]]:
        url = f"{self.BASE_URL_V3}/search/tv"
        params = {
            "query": query,
            "language": self.config.default_language,
            "include_adult": False,
            "api_key": self.config.api_key_v3,
        }
        try:
            resp = self._session.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            return [self._normalize_tv_result(r) for r in data.get("results", [])]
        except Exception:
            return []

    def _normalize_movie_result(self, result: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": str(result["id"]),
            "tmdb_id": result["id"],
            "type": "movie",
            "title": result.get("title", ""),
            "original_title": result.get("original_title", ""),
            "year": result.get("release_date", "")[:4] if result.get("release_date") else None,
            "poster_path": result.get("poster_path"),
            "backdrop_path": result.get("backdrop_path"),
            "overview": result.get("overview", ""),
            "popularity": result.get("popularity", 0),
            "vote_average": result.get("vote_average", 0),
            "media_type": "movie",
        }

    def _normalize_tv_result(self, result: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": str(result["id"]),
            "tmdb_id": result["id"],
            "type": "tv",
            "title": result.get("name", ""),
            "original_title": result.get("original_name", ""),
            "year": result.get("first_air_date", "")[:4] if result.get("first_air_date") else None,
            "poster_path": result.get("poster_path"),
            "backdrop_path": result.get("backdrop_path"),
            "overview": result.get("overview", ""),
            "popularity": result.get("popularity", 0),
            "vote_average": result.get("vote_average", 0),
            "media_type": "tv",
            "number_of_seasons": result.get("number_of_seasons", 0),
        }

    def get_movie_details(self, tmdb_id: int) -> Optional[dict[str, Any]]:
        """Get detailed movie info including credits (cast)."""
        url = f"{self.BASE_URL_V3}/movie/{tmdb_id}"
        params = {
            "language": self.config.default_language,
            "append_to_response": "credits",
            "api_key": self.config.api_key_v3,
        }
        try:
            resp = self._session.get(url, params=params, timeout=15)
            resp.raise_for_status()
            return self._normalize_movie_details(resp.json())
        except Exception:
            return None

    def get_tv_details(self, tmdb_id: int) -> Optional[dict[str, Any]]:
        """Get detailed TV show info including credits (cast)."""
        url = f"{self.BASE_URL_V3}/tv/{tmdb_id}"
        params = {
            "language": self.config.default_language,
            "append_to_response": "credits",
            "api_key": self.config.api_key_v3,
        }
        try:
            resp = self._session.get(url, params=params, timeout=15)
            resp.raise_for_status()
            return self._normalize_tv_details(resp.json())
        except Exception:
            return None

    def get_details(self, tmdb_id: int, media_type: str) -> Optional[dict[str, Any]]:
        """Get detailed info for a movie or TV show."""
        if media_type == "movie":
            return self.get_movie_details(tmdb_id)
        elif media_type == "tv":
            return self.get_tv_details(tmdb_id)
        return None

    def _normalize_movie_details(self, data: dict[str, Any]) -> dict[str, Any]:
        genres = [g["name"] for g in data.get("genres", [])]
        cast = self._normalize_credits(data.get("credits", {}))
        
        return {
            "tmdb_id": data["id"],
            "type": "movie",
            "title": data.get("title", ""),
            "original_title": data.get("original_title", ""),
            "year": data.get("release_date", "")[:4] if data.get("release_date") else None,
            "release_date": data.get("release_date"),
            "runtime": data.get("runtime"),
            "overview": data.get("overview", ""),
            "genres": genres,
            "poster_path": data.get("poster_path"),
            "backdrop_path": data.get("backdrop_path"),
            "vote_average": data.get("vote_average", 0),
            "origin_country": data.get("origin_country", []),
            "cast": cast,
        }

    def _normalize_tv_details(self, data: dict[str, Any]) -> dict[str, Any]:
        genres = [g["name"] for g in data.get("genres", [])]
        cast = self._normalize_credits(data.get("credits", {}))
        
        return {
            "tmdb_id": data["id"],
            "type": "tv",
            "title": data.get("name", ""),
            "original_title": data.get("original_name", ""),
            "year": data.get("first_air_date", "")[:4] if data.get("first_air_date") else None,
            "first_air_date": data.get("first_air_date"),
            "number_of_seasons": data.get("number_of_seasons", 0),
            "number_of_episodes": data.get("number_of_episodes", 0),
            "overview": data.get("overview", ""),
            "genres": genres,
            "poster_path": data.get("poster_path"),
            "backdrop_path": data.get("backdrop_path"),
            "vote_average": data.get("vote_average", 0),
            "origin_country": data.get("origin_country", []),
            "cast": cast,
        }

    def _normalize_credits(self, credits: dict[str, Any]) -> list[dict[str, Any]]:
        cast = []
        for member in credits.get("cast", [])[:30]:
            cast.append({
                "id": member.get("id"),
                "actor_name": member.get("name", ""),
                "character_name": member.get("character", ""),
                "profile_path": member.get("profile_path"),
                "order": member.get("order", 0),
            })
        return cast

    def get_poster_url(self, poster_path: str, size: str = "w342") -> str:
        """Get full URL for a poster image."""
        if not poster_path:
            return ""
        return f"{self.IMAGE_BASE_URL}/{size}{poster_path}"

    def download_poster(self, poster_path: str, size: str = "w500") -> Optional[str]:
        """Download poster to cache and return local file path."""
        if not poster_path:
            return None
        
        filename = f"{poster_path.lstrip('/').replace('/', '_')}"
        cache_path = POSTER_CACHE_DIR / filename
        
        if cache_path.exists():
            return str(cache_path)
        
        url = self.get_poster_url(poster_path, size)
        try:
            resp = self._session.get(url, timeout=30)
            resp.raise_for_status()
            with open(cache_path, "wb") as f:
                f.write(resp.content)
            return str(cache_path)
        except Exception:
            return None

    def tmdb_to_work(self, tmdb_data: dict[str, Any]) -> dict[str, Any]:
        """Convert TMDb details to canonical work format."""
        media_type = tmdb_data.get("media_type", tmdb_data.get("type", "movie"))
        work_type = "movie" if media_type == "movie" else "tv"
        
        metadata = {
            "poster_url": self.get_poster_url(tmdb_data.get("poster_path", "")),
            "overview": tmdb_data.get("overview", ""),
            "genres": tmdb_data.get("genres", []),
            "vote_average": tmdb_data.get("vote_average", 0),
            "source": "tmdb",
        }
        
        if tmdb_data.get("release_date"):
            metadata["release_date"] = tmdb_data["release_date"]
        if tmdb_data.get("first_air_date"):
            metadata["first_air_date"] = tmdb_data["first_air_date"]
        if tmdb_data.get("runtime"):
            metadata["runtime"] = tmdb_data["runtime"]
        if tmdb_data.get("origin_country"):
            metadata["origin_country"] = tmdb_data["origin_country"]
        
        cast_snapshot = []
        for member in tmdb_data.get("cast", []):
            cast_snapshot.append({
                "actor_name": member.get("actor_name", ""),
                "character_name": member.get("character_name", ""),
                "profile_url": self.get_poster_url(member.get("profile_path", "")),
            })
        
        return {
            "title": tmdb_data.get("title", ""),
            "type": work_type,
            "year": tmdb_data.get("year"),
            "external_refs": {
                "tmdb_id": tmdb_data.get("tmdb_id"),
                "tmdb_type": media_type,
            },
            "metadata": metadata,
            "cast_snapshot": cast_snapshot,
            "external_source": "tmdb",
        }


def get_tmdb_provider() -> TMDbProvider:
    """Get a singleton TMDb provider instance."""
    return TMDbProvider()
