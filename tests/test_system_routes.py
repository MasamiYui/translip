from __future__ import annotations

from pathlib import Path


def test_collect_model_statuses_detects_actual_cache_locations(tmp_path: Path) -> None:
    from translip.server.routes import system

    cache_root = tmp_path / "translip-cache"
    huggingface_cache_root = tmp_path / "huggingface" / "hub"

    (cache_root / "speechbrain" / "spkrec-ecapa-voxceleb").mkdir(parents=True)
    (cache_root / "transformers" / "models--facebook--m2m100_418M").mkdir(parents=True)
    (cache_root / "models" / "MOSS-TTS-Nano-100M-ONNX").mkdir(parents=True)
    (cache_root / "models" / "MOSS-Audio-Tokenizer-Nano-ONNX").mkdir(parents=True)
    (huggingface_cache_root / "models--Systran--faster-whisper-small").mkdir(parents=True)
    (huggingface_cache_root / "models--Qwen--Qwen3-TTS-12Hz-0.6B-Base").mkdir(parents=True)

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


def test_collect_model_statuses_detects_cdx23_weights_in_runtime_cache(tmp_path: Path) -> None:
    from translip.server.routes import system

    cache_root = tmp_path / "translip-cache"
    huggingface_cache_root = tmp_path / "huggingface" / "hub"

    cdx23_dir = cache_root / "models" / "cdx23"
    cdx23_dir.mkdir(parents=True)
    (cdx23_dir / "97d170e1-dbb4db15.th").write_bytes(b"weights")

    models = system.collect_model_statuses(
        cache_root=cache_root,
        huggingface_cache_root=huggingface_cache_root,
    )

    status_by_name = {item["name"]: item["status"] for item in models}

    assert status_by_name["CDX23 weights"] == "available"
