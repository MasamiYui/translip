from __future__ import annotations

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


def test_browse_filesystem_lists_dirs_and_media_only(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from translip.server.app import app

    (tmp_path / "sub").mkdir()
    (tmp_path / "clip.mp4").write_bytes(b"video")
    (tmp_path / "track.wav").write_bytes(b"audio")
    (tmp_path / "notes.txt").write_text("ignored")
    (tmp_path / ".hidden.mp4").write_bytes(b"hidden")

    client = TestClient(app)
    resp = client.get("/api/system/browse", params={"path": str(tmp_path)})
    assert resp.status_code == 200
    body = resp.json()

    assert body["path"] == str(tmp_path.resolve())
    names = [e["name"] for e in body["entries"]]
    # Directories first, then media files; non-media and hidden entries excluded.
    assert names == ["sub", "clip.mp4", "track.wav"]
    assert body["entries"][0]["is_dir"] is True
    assert body["entries"][1]["is_media"] is True


def test_browse_filesystem_passing_file_opens_parent(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from translip.server.app import app

    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"video")

    client = TestClient(app)
    resp = client.get("/api/system/browse", params={"path": str(clip)})
    assert resp.status_code == 200
    assert resp.json()["path"] == str(tmp_path.resolve())


def test_browse_filesystem_missing_path_returns_404(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from translip.server.app import app

    client = TestClient(app)
    resp = client.get("/api/system/browse", params={"path": str(tmp_path / "nope")})
    assert resp.status_code == 404


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
