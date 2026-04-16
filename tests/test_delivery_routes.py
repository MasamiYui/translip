from __future__ import annotations

from fastapi.testclient import TestClient

from translip.server.app import app


def test_delivery_routes_are_registered() -> None:
    client = TestClient(app)
    paths = {route.path for route in app.routes}
    assert "/api/tasks/{task_id}/subtitle-preview" in paths
    assert "/api/tasks/{task_id}/delivery-compose" in paths
