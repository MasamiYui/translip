from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace


def test_transcription_adapter_copies_artifacts_and_summarizes_segments(
    tmp_path: Path, monkeypatch
) -> None:
    from translip.server.atomic_tools.adapters.transcription import TranscriptionAdapter

    input_file = tmp_path / "input" / "file" / "demo.wav"
    input_file.parent.mkdir(parents=True, exist_ok=True)
    input_file.write_bytes(b"audio")
    output_dir = tmp_path / "output"

    def fake_transcribe_file(request):
        bundle_dir = tmp_path / "runner-output" / "demo"
        bundle_dir.mkdir(parents=True, exist_ok=True)
        segments_path = bundle_dir / "segments.zh.json"
        segments_path.write_text(json.dumps({"segments": []}), encoding="utf-8")
        srt_path = bundle_dir / "segments.zh.srt"
        srt_path.write_text("1\n00:00:00,000 --> 00:00:01,000\nhello\n", encoding="utf-8")
        return SimpleNamespace(
            media_info=SimpleNamespace(duration_sec=8.5),
            segments=[
                SimpleNamespace(segment_id="seg-1", start=0.0, end=1.0, text="你好", speaker_label="SPEAKER_00"),
                SimpleNamespace(segment_id="seg-2", start=1.0, end=2.5, text="世界", speaker_label="SPEAKER_01"),
            ],
            artifacts=SimpleNamespace(
                segments_json_path=segments_path,
                srt_path=srt_path,
                manifest_path=bundle_dir / "task-a-manifest.json",
            ),
        )

    monkeypatch.setattr(
        "translip.server.atomic_tools.adapters.transcription.transcribe_file",
        fake_transcribe_file,
    )

    result = TranscriptionAdapter().run(
        {"file_id": "fake", "language": "zh", "asr_model": "small", "generate_srt": True},
        input_file.parent.parent,
        output_dir,
        lambda *_args, **_kwargs: None,
    )

    assert (output_dir / "segments.zh.json").exists()
    assert (output_dir / "segments.zh.srt").exists()
    assert result["total_segments"] == 2
    assert result["speaker_count"] == 2
    assert result["has_srt"] is True
    assert result["segments_file"] == "segments.zh.json"


def test_transcription_adapter_uses_requested_language_in_artifact_names(
    tmp_path: Path, monkeypatch
) -> None:
    from translip.server.atomic_tools.adapters.transcription import TranscriptionAdapter

    input_file = tmp_path / "input" / "file" / "demo.wav"
    input_file.parent.mkdir(parents=True, exist_ok=True)
    input_file.write_bytes(b"audio")
    output_dir = tmp_path / "output"

    def fake_transcribe_file(request):
        assert request.language == "ja"
        bundle_dir = tmp_path / "runner-output" / "demo"
        bundle_dir.mkdir(parents=True, exist_ok=True)
        segments_path = bundle_dir / "segments.zh.json"
        segments_path.write_text(json.dumps({"segments": []}), encoding="utf-8")
        srt_path = bundle_dir / "segments.zh.srt"
        srt_path.write_text("1\n00:00:00,000 --> 00:00:01,000\nこんにちは\n", encoding="utf-8")
        return SimpleNamespace(
            media_info=SimpleNamespace(duration_sec=8.5),
            segments=[
                SimpleNamespace(segment_id="seg-1", start=0.0, end=1.0, text="こんにちは", speaker_label="SPEAKER_00"),
            ],
            artifacts=SimpleNamespace(
                segments_json_path=segments_path,
                srt_path=srt_path,
                manifest_path=bundle_dir / "task-a-manifest.json",
            ),
        )

    monkeypatch.setattr(
        "translip.server.atomic_tools.adapters.transcription.transcribe_file",
        fake_transcribe_file,
    )

    result = TranscriptionAdapter().run(
        {"file_id": "fake", "language": "ja", "asr_model": "small", "generate_srt": True},
        input_file.parent.parent,
        output_dir,
        lambda *_args, **_kwargs: None,
    )

    assert (output_dir / "segments.ja.json").exists()
    assert (output_dir / "segments.ja.srt").exists()
    assert result["language"] == "ja"
    assert result["segments_file"] == "segments.ja.json"
    assert result["srt_file"] == "segments.ja.srt"
