from __future__ import annotations

import os
from pathlib import Path

import pytest


def test_collect_model_statuses_detects_actual_cache_locations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from translip.server.routes import system

    cache_root = tmp_path / "translip-cache"
    huggingface_cache_root = tmp_path / "huggingface" / "hub"
    modelscope_cache_root = tmp_path / "modelscope" / "hub"
    monkeypatch.setenv("MODELSCOPE_CACHE", str(modelscope_cache_root))

    (cache_root / "speechbrain" / "spkrec-ecapa-voxceleb").mkdir(parents=True)
    (cache_root / "transformers" / "models--facebook--m2m100_418M").mkdir(parents=True)
    (cache_root / "models" / "MOSS-TTS-Nano-100M-ONNX").mkdir(parents=True)
    (cache_root / "models" / "MOSS-Audio-Tokenizer-Nano-ONNX").mkdir(parents=True)
    (huggingface_cache_root / "models--Systran--faster-whisper-small").mkdir(parents=True)
    (huggingface_cache_root / "models--Qwen--Qwen3-TTS-12Hz-0.6B-Base").mkdir(parents=True)
    (huggingface_cache_root / "models--pyannote--speaker-diarization-3.1").mkdir(parents=True)
    (huggingface_cache_root / "models--pyannote--segmentation-3.0").mkdir(parents=True)
    (modelscope_cache_root / "iic" / "SenseVoiceSmall").mkdir(parents=True)
    (modelscope_cache_root / "iic" / "speech_fsmn_vad_zh-cn-16k-common-pytorch").mkdir(parents=True)

    models = system.collect_model_statuses(
        cache_root=cache_root,
        huggingface_cache_root=huggingface_cache_root,
    )

    status_by_name = {item["name"]: item["status"] for item in models}

    assert status_by_name["SpeechBrain ECAPA"] == "available"
    assert status_by_name["M2M100 418M"] == "available"
    assert status_by_name["faster-whisper small"] == "available"
    assert status_by_name["MOSS-TTS-Nano ONNX"] == "available"
    assert status_by_name["Qwen3TTS"] == "available"
    assert status_by_name["CDX23 weights"] == "missing"
    assert status_by_name["pyannote speaker-diarization 3.1"] == "available"
    assert status_by_name["pyannote segmentation 3.0"] == "available"
    assert status_by_name["FunASR SenseVoiceSmall"] == "available"
    assert status_by_name["FunASR FSMN-VAD"] == "available"
    assert status_by_name["FunASR CT-Punc"] == "missing"


def test_collect_model_statuses_detects_cdx23_weights_in_runtime_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from translip.server.routes import system

    cache_root = tmp_path / "translip-cache"
    huggingface_cache_root = tmp_path / "huggingface" / "hub"
    modelscope_cache_root = tmp_path / "modelscope" / "hub"
    monkeypatch.setenv("MODELSCOPE_CACHE", str(modelscope_cache_root))

    cdx23_dir = cache_root / "models" / "cdx23"
    cdx23_dir.mkdir(parents=True)
    (cdx23_dir / "97d170e1-dbb4db15.th").write_bytes(b"weights")

    models = system.collect_model_statuses(
        cache_root=cache_root,
        huggingface_cache_root=huggingface_cache_root,
    )

    status_by_name = {item["name"]: item["status"] for item in models}

    assert status_by_name["CDX23 weights"] == "available"
    assert status_by_name["pyannote speaker-diarization 3.1"] == "missing"
    assert status_by_name["FunASR SenseVoiceSmall"] == "missing"


def test_pick_file_returns_selected_path(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient

    from translip.server.app import app
    from translip.server.routes import system

    monkeypatch.setattr(
        system, "_open_native_file_dialog", lambda *a, **k: "/videos/clip.mp4"
    )

    client = TestClient(app)
    resp = client.post("/api/system/pick-file", json={"initial_path": "/videos"})
    assert resp.status_code == 200
    assert resp.json() == {"path": "/videos/clip.mp4", "cancelled": False}


def test_pick_file_cancelled_returns_null(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient

    from translip.server.app import app
    from translip.server.routes import system

    monkeypatch.setattr(system, "_open_native_file_dialog", lambda *a, **k: None)

    client = TestClient(app)
    resp = client.post("/api/system/pick-file", json={})
    assert resp.status_code == 200
    assert resp.json() == {"path": None, "cancelled": True}


def test_pick_file_unavailable_returns_501(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient

    from translip.server.app import app
    from translip.server.routes import system

    def _boom(*_a, **_k):
        raise RuntimeError("no_dialog_helper")

    monkeypatch.setattr(system, "_open_native_file_dialog", _boom)

    client = TestClient(app)
    resp = client.post("/api/system/pick-file", json={})
    assert resp.status_code == 501


def test_resolve_initial_dir_uses_parent_for_file(tmp_path: Path) -> None:
    from translip.server.routes import system

    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"video")

    assert system._resolve_initial_dir(str(clip)) == str(tmp_path)
    assert system._resolve_initial_dir(str(tmp_path)) == str(tmp_path)
    assert system._resolve_initial_dir(str(tmp_path / "missing" / "x.mp4")) is None
    assert system._resolve_initial_dir(None) is None


def _clear_hf_tokens(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Clear HF token env vars and isolate the user-config store to a temp path.

    `_resolve_hf_token()` also reads the persisted `hf_token` user setting, so
    tests must point that store at an empty temp file to stay deterministic.
    """
    from translip.server import cache_manager

    for env_name in ("HF_TOKEN", "HUGGINGFACE_HUB_TOKEN", "PYANNOTE_AUTH_TOKEN"):
        monkeypatch.delenv(env_name, raising=False)
    monkeypatch.setattr(
        cache_manager, "_USER_CONFIG_PATH", tmp_path / "settings.json"
    )


def test_auto_downloadable_includes_funasr_modelscope_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from translip.server import cache_manager

    _clear_hf_tokens(monkeypatch, tmp_path)

    assert cache_manager.is_auto_downloadable("funasr_sensevoice_small")
    assert cache_manager.is_auto_downloadable("funasr_fsmn_vad")
    assert cache_manager.is_auto_downloadable("funasr_ct_punc")
    assert cache_manager.is_auto_downloadable("faster_whisper_small")
    assert not cache_manager.is_auto_downloadable("cdx23")
    # Gated repos hidden when no HF token is present.
    assert not cache_manager.is_auto_downloadable("pyannote_speaker_diarization_31")
    assert not cache_manager.is_auto_downloadable("pyannote_segmentation_30")


def test_auto_downloadable_includes_gated_keys_when_token_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from translip.server import cache_manager

    _clear_hf_tokens(monkeypatch, tmp_path)
    monkeypatch.setenv("HF_TOKEN", "hf_dummy_token")

    assert cache_manager.is_auto_downloadable("pyannote_speaker_diarization_31")
    assert cache_manager.is_auto_downloadable("pyannote_segmentation_30")


def test_saved_hf_token_makes_gated_keys_downloadable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A token persisted via the settings UI (no env var) unlocks gated models."""
    from translip.server import cache_manager

    _clear_hf_tokens(monkeypatch, tmp_path)

    # No token yet -> gated models stay hidden.
    assert not cache_manager.is_auto_downloadable("pyannote_speaker_diarization_31")

    cache_manager.update_user_setting("hf_token", "hf_saved_token")

    assert cache_manager._resolve_hf_token() == "hf_saved_token"
    assert cache_manager.is_auto_downloadable("pyannote_speaker_diarization_31")
    assert cache_manager.is_auto_downloadable("pyannote_segmentation_30")

    # Clearing it (empty string semantics) hides them again.
    cache_manager.update_user_setting("hf_token", None)
    assert not cache_manager.is_auto_downloadable("pyannote_speaker_diarization_31")


def test_hf_token_endpoints_roundtrip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fastapi.testclient import TestClient

    from translip.server import cache_manager
    from translip.server.app import app

    _clear_hf_tokens(monkeypatch, tmp_path)
    client = TestClient(app)

    assert client.get("/api/system/hf-token").json() == {"ok": True, "hf_token_set": False}

    resp = client.post("/api/system/hf-token", json={"hf_token": "  hf_from_ui  "})
    assert resp.json() == {"ok": True, "hf_token_set": True}
    # Stored trimmed, and now resolvable for downloads.
    assert cache_manager.read_user_setting("hf_token") == "hf_from_ui"
    assert client.get("/api/system/hf-token").json()["hf_token_set"] is True

    # Empty string clears it.
    resp = client.post("/api/system/hf-token", json={"hf_token": ""})
    assert resp.json() == {"ok": True, "hf_token_set": False}
    assert cache_manager.read_user_setting("hf_token") is None


def test_start_missing_dispatches_to_modelscope_for_funasr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from translip.server import cache_manager

    _clear_hf_tokens(monkeypatch, tmp_path)
    monkeypatch.setenv("MODELSCOPE_CACHE", str(tmp_path / "modelscope" / "hub"))
    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path / "huggingface" / "hub"))
    monkeypatch.setattr(
        cache_manager, "resolve_active_cache_root", lambda: tmp_path / "translip-cache"
    )

    hf_calls: list[dict] = []
    ms_calls: list[dict] = []

    def fake_hf(**kwargs):
        hf_calls.append(kwargs)
        return None

    def fake_ms(**kwargs):
        ms_calls.append(kwargs)
        return None

    monkeypatch.setattr(cache_manager, "_hf_snapshot_download", fake_hf)
    monkeypatch.setattr(cache_manager, "_ms_snapshot_download", fake_ms)

    job = cache_manager.model_download_manager.start_missing(
        run_in_thread=False,
        only_keys=["funasr_sensevoice_small", "funasr_fsmn_vad"],
    )

    assert job.state == "succeeded"
    assert {it.key for it in job.items.values()} == {
        "funasr_sensevoice_small",
        "funasr_fsmn_vad",
    }
    assert all(it.state == "succeeded" for it in job.items.values())
    assert hf_calls == []  # FunASR should never go through HF
    assert {c["model_id"] for c in ms_calls} == {
        "iic/SenseVoiceSmall",
        "iic/speech_fsmn_vad_zh-cn-16k-common-pytorch",
    }


def test_start_missing_rejects_gated_keys_without_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from translip.server import cache_manager

    _clear_hf_tokens(monkeypatch, tmp_path)
    monkeypatch.setattr(
        cache_manager, "resolve_active_cache_root", lambda: tmp_path / "translip-cache"
    )

    monkeypatch.setattr(cache_manager, "_hf_snapshot_download", lambda **_: None)
    monkeypatch.setattr(cache_manager, "_ms_snapshot_download", lambda **_: None)

    with pytest.raises(cache_manager.ModelDownloadError):
        cache_manager.model_download_manager.start_missing(
            run_in_thread=False,
            only_keys=["pyannote_speaker_diarization_31"],
        )


def test_start_missing_passes_token_for_gated_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from translip.server import cache_manager

    _clear_hf_tokens(monkeypatch, tmp_path)
    monkeypatch.setenv("HF_TOKEN", "hf_dummy_token")
    monkeypatch.setattr(
        cache_manager, "resolve_active_cache_root", lambda: tmp_path / "translip-cache"
    )

    captured: list[dict] = []
    monkeypatch.setattr(
        cache_manager, "_hf_snapshot_download", lambda **kw: captured.append(kw)
    )
    monkeypatch.setattr(cache_manager, "_ms_snapshot_download", lambda **_: None)

    job = cache_manager.model_download_manager.start_missing(
        run_in_thread=False,
        only_keys=["pyannote_speaker_diarization_31"],
    )

    assert job.state == "succeeded"
    assert captured and captured[0]["repo_id"] == "pyannote/speaker-diarization-3.1"
    assert captured[0].get("token") == "hf_dummy_token"


# ---------------------------------------------------------------------------
# PaddleOCR (hard-subtitle OCR) — three-way status + local-dir downloader
# ---------------------------------------------------------------------------


def test_paddleocr_status_needs_extra_when_extra_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from translip.server import cache_manager

    monkeypatch.setattr(cache_manager, "_paddleocr_extra_installed", lambda: False)
    # Weights presence is irrelevant when the extra can't be imported.
    monkeypatch.setattr(cache_manager, "_paddleocr_weights_present", lambda: True)

    assert cache_manager._paddleocr_status(tmp_path, tmp_path) == "needs_extra"


def test_paddleocr_status_missing_then_available_with_extra(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from translip.server import cache_manager

    monkeypatch.setattr(cache_manager, "_paddleocr_extra_installed", lambda: True)

    monkeypatch.setattr(cache_manager, "_paddleocr_weights_present", lambda: False)
    assert cache_manager._paddleocr_status(tmp_path, tmp_path) == "missing"

    monkeypatch.setattr(cache_manager, "_paddleocr_weights_present", lambda: True)
    assert cache_manager._paddleocr_status(tmp_path, tmp_path) == "available"


def test_collect_model_statuses_reports_paddleocr_needs_extra(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from translip.server import cache_manager
    from translip.server.routes import system

    monkeypatch.setattr(cache_manager, "_paddleocr_extra_installed", lambda: False)

    models = system.collect_model_statuses(
        cache_root=tmp_path / "translip-cache",
        huggingface_cache_root=tmp_path / "huggingface" / "hub",
    )
    entry = next(m for m in models if m["name"] == "PaddleOCR (hard-subtitle OCR)")
    assert entry["status"] == "needs_extra"
    assert entry["detail"] == "ocr_extra_missing"


def test_paddleocr_is_auto_downloadable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from translip.server import cache_manager

    _clear_hf_tokens(monkeypatch, tmp_path)
    # Public Apache-2.0 weights — eligible without any HF token.
    assert cache_manager.is_auto_downloadable("paddleocr_models")


def test_list_missing_excludes_paddleocr_when_needs_extra(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from translip.server import cache_manager

    cache_root = tmp_path / "translip-cache"
    hf_root = tmp_path / "huggingface" / "hub"

    # needs_extra: downloader can't help -> not in the missing/downloadable list.
    monkeypatch.setattr(cache_manager, "_paddleocr_extra_installed", lambda: False)
    missing = cache_manager.list_missing_model_keys(
        cache_root=cache_root, huggingface_cache_root=hf_root
    )
    assert "paddleocr_models" not in missing

    # extra installed but weights absent -> downloadable, so it IS listed.
    monkeypatch.setattr(cache_manager, "_paddleocr_extra_installed", lambda: True)
    monkeypatch.setattr(cache_manager, "_paddleocr_weights_present", lambda: False)
    missing = cache_manager.list_missing_model_keys(
        cache_root=cache_root, huggingface_cache_root=hf_root
    )
    assert "paddleocr_models" in missing


def test_start_missing_downloads_paddleocr_into_local_layout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from translip.server import cache_manager

    _clear_hf_tokens(monkeypatch, tmp_path)
    monkeypatch.setattr(
        cache_manager, "resolve_active_cache_root", lambda: tmp_path / "translip-cache"
    )
    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path / "huggingface" / "hub"))

    base = tmp_path / "translip-cache" / "paddleocr_models" / "macos-arm64"
    specs = [
        ("PaddlePaddle/PP-OCRv5_mobile_det", base / "PP-OCRv5_mobile_det"),
        ("PaddlePaddle/PP-OCRv5_mobile_rec", base / "PP-OCRv5_mobile_rec"),
    ]
    monkeypatch.setattr(cache_manager, "_paddleocr_download_specs", lambda: specs)

    calls: list[dict] = []
    monkeypatch.setattr(
        cache_manager, "_hf_snapshot_download", lambda **kw: calls.append(kw)
    )
    monkeypatch.setattr(cache_manager, "_ms_snapshot_download", lambda **_: None)

    job = cache_manager.model_download_manager.start_missing(
        run_in_thread=False,
        only_keys=["paddleocr_models"],
    )

    assert job.state == "succeeded"
    assert job.items["paddleocr_models"].state == "succeeded"
    # Each repo fetched directly into its local layout dir (not the HF hub cache).
    assert [c["repo_id"] for c in calls] == [s[0] for s in specs]
    assert [c["local_dir"] for c in calls] == [str(s[1]) for s in specs]
    assert all("cache_dir" not in c for c in calls)
    # Target dirs are created before the fetch.
    assert all(target.exists() for _, target in specs)


def _clear_llm_keys(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Clear LLM provider env vars and isolate the user-config store to a temp path."""
    from translip.server import cache_manager

    for env_name in ("DEEPSEEK_API_KEY", "SILICONFLOW_API_KEY"):
        monkeypatch.delenv(env_name, raising=False)
    monkeypatch.setattr(cache_manager, "_USER_CONFIG_PATH", tmp_path / "settings.json")


def test_llm_keys_endpoints_roundtrip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fastapi.testclient import TestClient

    from translip.server import cache_manager
    from translip.server.app import app

    _clear_llm_keys(monkeypatch, tmp_path)
    client = TestClient(app)

    assert client.get("/api/system/llm-keys").json() == {
        "ok": True,
        "providers": {"deepseek": False, "siliconflow": False},
    }

    resp = client.post("/api/system/llm-keys", json={"provider": "deepseek", "api_key": "  sk-abc  "})
    assert resp.json() == {"ok": True, "provider": "deepseek", "set": True}
    # Stored trimmed and bridged into the environment for task subprocesses.
    assert cache_manager.read_user_setting("deepseek_api_key") == "sk-abc"
    assert os.environ["DEEPSEEK_API_KEY"] == "sk-abc"
    assert client.get("/api/system/llm-keys").json()["providers"]["deepseek"] is True
    # The other provider stays unset.
    assert client.get("/api/system/llm-keys").json()["providers"]["siliconflow"] is False

    # Empty string clears the key and removes the value we bridged into env.
    resp = client.post("/api/system/llm-keys", json={"provider": "deepseek", "api_key": ""})
    assert resp.json() == {"ok": True, "provider": "deepseek", "set": False}
    assert cache_manager.read_user_setting("deepseek_api_key") is None
    assert "DEEPSEEK_API_KEY" not in os.environ


def test_llm_keys_rejects_unknown_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fastapi.testclient import TestClient

    from translip.server.app import app

    _clear_llm_keys(monkeypatch, tmp_path)
    client = TestClient(app)

    assert client.post("/api/system/llm-keys", json={"provider": "openai", "api_key": "x"}).status_code == 400
    assert client.post("/api/system/llm-keys/test", json={"provider": "openai"}).status_code == 400


def test_llm_key_test_endpoint_uses_saved_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fastapi.testclient import TestClient

    from translip.server import cache_manager
    from translip.server.app import app
    from translip.transcription import arbitration

    _clear_llm_keys(monkeypatch, tmp_path)
    client = TestClient(app)

    seen: list[tuple[str, str | None]] = []

    def fake_test_provider(mode: str, *, api_key: str | None = None, timeout_sec: int = 20):
        seen.append((mode, api_key))
        return {"ok": True, "model": "deepseek-chat", "message": "OK"}

    monkeypatch.setattr(arbitration, "test_provider", fake_test_provider)

    # With no inline key, the route falls back to the saved/env key.
    cache_manager.set_llm_key("deepseek", "sk-saved")
    resp = client.post("/api/system/llm-keys/test", json={"provider": "deepseek"})
    assert resp.json() == {
        "ok": True,
        "provider": "deepseek",
        "model": "deepseek-chat",
        "message": "OK",
    }
    assert seen[-1] == ("deepseek", "sk-saved")

    # An inline key takes precedence over the saved one.
    client.post("/api/system/llm-keys/test", json={"provider": "deepseek", "api_key": "sk-inline"})
    assert seen[-1] == ("deepseek", "sk-inline")


def test_apply_llm_keys_to_env_bridges_saved_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from translip.server import cache_manager

    _clear_llm_keys(monkeypatch, tmp_path)
    # Persist a key directly (as if saved in a prior session) without touching env.
    cache_manager.update_user_setting("siliconflow_api_key", "sk-persisted")
    assert "SILICONFLOW_API_KEY" not in os.environ

    cache_manager.apply_llm_keys_to_env()
    assert os.environ["SILICONFLOW_API_KEY"] == "sk-persisted"

    # An env var already present is never overwritten.
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-from-operator")
    cache_manager.update_user_setting("deepseek_api_key", "sk-other")
    cache_manager.apply_llm_keys_to_env()
    assert os.environ["DEEPSEEK_API_KEY"] == "sk-from-operator"


def test_hf_token_test_endpoint_uses_saved_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fastapi.testclient import TestClient

    from translip.server import cache_manager
    from translip.server.app import app
    from translip.server.routes import system

    _clear_hf_tokens(monkeypatch, tmp_path)
    client = TestClient(app)

    seen: list[str | None] = []

    def fake_verify(token, *, timeout_sec: int = 15):
        seen.append(token)
        return {"ok": True, "message": "OK (alice)"}

    monkeypatch.setattr(system, "_verify_hf_token", fake_verify)

    # No inline token -> falls back to the saved token.
    cache_manager.update_user_setting("hf_token", "hf_saved")
    resp = client.post("/api/system/hf-token/test", json={})
    assert resp.json() == {"ok": True, "message": "OK (alice)"}
    assert seen[-1] == "hf_saved"

    # Inline token wins over the saved one.
    client.post("/api/system/hf-token/test", json={"hf_token": "hf_inline"})
    assert seen[-1] == "hf_inline"


def test_hf_token_test_endpoint_no_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fastapi.testclient import TestClient

    from translip.server.app import app

    _clear_hf_tokens(monkeypatch, tmp_path)
    client = TestClient(app)

    # Nothing saved, nothing provided -> not ok, no network call.
    body = client.post("/api/system/hf-token/test", json={}).json()
    assert body["ok"] is False
    assert body["message"]


def test_tmdb_test_endpoint_prefers_inline_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fastapi.testclient import TestClient

    from translip.server.app import app
    from translip.speaker_review.works_providers import tmdb

    monkeypatch.delenv("TMDB_API_KEY", raising=False)
    monkeypatch.delenv("TMDB_BEARER_TOKEN", raising=False)
    client = TestClient(app)

    seen: list[tuple[str, str]] = []

    def fake_verify(*, api_key_v3: str = "", api_key_v4: str = "", timeout: int = 10):
        seen.append((api_key_v3, api_key_v4))
        return {"ok": True, "message": "OK"}

    monkeypatch.setattr(tmdb, "verify_credentials", fake_verify)

    resp = client.post(
        "/api/config/tmdb/test", json={"api_key_v3": "v3key", "api_key_v4": "v4key"}
    )
    assert resp.json() == {"ok": True, "message": "OK"}
    assert seen[-1] == ("v3key", "v4key")
