from __future__ import annotations

import json
from pathlib import Path


def test_detect_language_returns_ranked_candidates(tmp_path: Path, monkeypatch) -> None:
    from translip.server.atomic_tools.adapters import detect_language as mod

    input_dir = tmp_path / "input" / "file"
    input_dir.mkdir(parents=True)
    (input_dir / "clip.mp4").write_bytes(b"video")
    output_dir = tmp_path / "output"

    captured: dict = {}

    def fake_detect(audio_path, *, model_name, requested_device, windows):
        captured.update(model_name=model_name, windows=windows, requested_device=requested_device)
        candidates = [("ja", 0.9741), ("zh", 0.0112), ("ko", 0.0061), ("en", 0.003)]
        return "ja", 0.9741, candidates, {
            "asr_backend": "faster-whisper",
            "asr_model": model_name,
            "windows_analyzed": windows,
        }

    monkeypatch.setattr(mod, "detect_audio_language", fake_detect)

    result = mod.DetectLanguageAdapter().run(
        {"file_id": "f", "model": "medium", "windows": 3},
        tmp_path / "input",
        output_dir,
        lambda *_a, **_k: None,
    )

    assert captured == {"model_name": "medium", "windows": 3, "requested_device": "auto"}
    assert result["language"] == "ja"
    assert result["language_name"] == "日语"
    assert result["confidence"] == 0.9741
    assert result["is_confident"] is True
    # Ranked, name-mapped, capped at top 5.
    assert [c["language"] for c in result["candidates"]] == ["ja", "zh", "ko", "en"]
    assert result["candidates"][1]["language_name"] == "中文"
    assert result["windows_analyzed"] == 3
    # Persisted artifact mirrors the returned payload.
    assert json.loads((output_dir / "language.json").read_text())["language"] == "ja"


def test_detect_language_flags_low_confidence(tmp_path: Path, monkeypatch) -> None:
    from translip.server.atomic_tools.adapters import detect_language as mod

    input_dir = tmp_path / "input" / "file"
    input_dir.mkdir(parents=True)
    (input_dir / "clip.wav").write_bytes(b"audio")

    monkeypatch.setattr(
        mod, "detect_audio_language",
        lambda *a, **k: ("xx", 0.34, [("xx", 0.34), ("zh", 0.30)], {
            "asr_backend": "faster-whisper", "asr_model": "tiny", "windows_analyzed": 1,
        }),
    )

    result = mod.DetectLanguageAdapter().run(
        {"file_id": "f", "model": "tiny", "windows": 1},
        tmp_path / "input",
        tmp_path / "output",
        lambda *_a, **_k: None,
    )

    assert result["is_confident"] is False
    # Unmapped code falls back to its upper-cased ISO form.
    assert result["language_name"] == "XX"
