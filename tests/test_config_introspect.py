from __future__ import annotations

from translip.server.config_introspect import CONFIG_KNOBS, introspect_config


def _by_key(rows: list[dict]) -> dict[str, dict]:
    return {row["key"]: row for row in rows}


def test_all_knobs_default_when_environ_empty() -> None:
    rows = introspect_config(environ={})
    assert len(rows) == len(CONFIG_KNOBS)
    for row in rows:
        assert row["source"] == "default"
        assert row["is_overridden"] is False


def test_env_override_is_reported_with_value() -> None:
    rows = _by_key(introspect_config(environ={"DEEPSEEK_BASE_URL": "https://proxy.example/v1"}))
    base = rows["deepseek_base_url"]
    assert base["source"] == "env"
    assert base["is_overridden"] is True
    assert base["value"] == "https://proxy.example/v1"
    # An unset knob stays default.
    assert rows["ffmpeg_binary"]["source"] == "default"
    assert rows["ffmpeg_binary"]["value"] == "ffmpeg"


def test_secret_values_are_masked_never_leaked() -> None:
    secret = "sk-super-secret-value-123"
    rows = _by_key(introspect_config(environ={"DEEPSEEK_API_KEY": secret, "HF_TOKEN": secret}))

    api_key = rows["deepseek_api_key"]
    assert api_key["secret"] is True
    assert api_key["is_overridden"] is True
    assert api_key["value"] == "set"  # masked, not the real value
    assert api_key["default"] is None

    # The raw secret must never appear anywhere in the output.
    import json

    assert secret not in json.dumps(rows)


def test_unset_secret_reports_none() -> None:
    rows = _by_key(introspect_config(environ={}))
    api_key = rows["deepseek_api_key"]
    assert api_key["secret"] is True
    assert api_key["value"] is None
    assert api_key["is_overridden"] is False


def test_effective_config_endpoint(monkeypatch) -> None:
    from fastapi.testclient import TestClient

    from translip.server.app import app

    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-endpoint-secret")
    with TestClient(app) as client:
        response = client.get("/api/system/config/effective")
    assert response.status_code == 200
    payload = response.json()
    assert "knobs" in payload
    keys = {knob["key"] for knob in payload["knobs"]}
    assert "deepseek_base_url" in keys
    # Endpoint must not leak the secret value either.
    assert "sk-endpoint-secret" not in response.text
