from __future__ import annotations

from pathlib import Path

from translip.server import app as app_module


def test_frontend_dist_path_points_to_repo_frontend_dist() -> None:
    expected = Path(__file__).resolve().parents[1] / "frontend" / "dist"

    assert app_module._FRONTEND_DIST == expected
    assert app_module._FRONTEND_DIST.exists()
