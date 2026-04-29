import json
from pathlib import Path

import numpy as np

from translip.transcription.export import (
    build_transcription_manifest,
    segments_payload,
    write_segments_srt,
)
from translip.transcription.speaker import _cluster_embeddings, _expanded_window, _stable_relabel
from translip.types import MediaInfo, TranscriptionRequest, TranscriptionSegment
from translip.transcription.asr import AsrSegment, resolve_faster_whisper_model_path


def test_stable_relabel_preserves_first_seen_order() -> None:
    assert _stable_relabel([5, 5, 7, 5, 3]) == [
        "SPEAKER_00",
        "SPEAKER_00",
        "SPEAKER_01",
        "SPEAKER_00",
        "SPEAKER_02",
    ]


def test_cluster_embeddings_merges_high_similarity_vectors() -> None:
    embeddings = np.array(
        [
            [1.0, 0.0, 0.0],
            [0.98, 0.05, 0.0],
            [0.0, 1.0, 0.0],
        ],
        dtype=np.float32,
    )
    embeddings /= np.linalg.norm(embeddings, axis=1, keepdims=True)
    labels = _cluster_embeddings(embeddings)
    assert labels[0] == labels[1]
    assert labels[0] != labels[2]


def test_expanded_window_hits_min_duration() -> None:
    segment = AsrSegment(
        segment_id="seg-0001",
        start=1.0,
        end=1.3,
        text="你好",
        language="zh",
    )
    window = _expanded_window(segment, audio_duration=10.0)
    assert round(window.end - window.start, 3) >= 1.6


def test_segments_payload_and_manifest_shape(tmp_path: Path) -> None:
    request = TranscriptionRequest(input_path="voice.wav").normalized()
    media_info = MediaInfo(
        path=Path("/tmp/voice.wav"),
        media_type="audio",
        format_name="wav",
        duration_sec=12.0,
        audio_stream_index=0,
        audio_stream_count=1,
        sample_rate=16000,
        channels=1,
    )
    segments = [
        TranscriptionSegment(
            segment_id="seg-0001",
            start=0.0,
            end=1.5,
            text="你好，世界。",
            speaker_label="SPEAKER_00",
            language="zh",
            duration=1.5,
        )
    ]
    payload = segments_payload(
        request=request,
        media_info=media_info,
        segments=segments,
        metadata={
            "asr_backend": "faster-whisper",
            "asr_model": "small",
            "asr_device": "cpu",
            "speaker_backend": "speechbrain-ecapa",
            "speaker_device": "cpu",
            "detected_language": "zh",
        },
    )
    manifest = build_transcription_manifest(
        request=request,
        media_info=media_info,
        segments_path=tmp_path / "segments.zh.json",
        srt_path=tmp_path / "segments.zh.srt",
        started_at="2026-04-11T22:00:00+08:00",
        finished_at="2026-04-11T22:00:01+08:00",
        elapsed_sec=1.0,
        metadata={"segment_count": 1, "speaker_count": 1},
    )
    payload_json = json.loads(json.dumps(payload, ensure_ascii=False))
    manifest_json = json.loads(json.dumps(manifest, ensure_ascii=False))
    assert payload_json["stats"]["segment_count"] == 1
    assert payload_json["segments"][0]["speaker_label"] == "SPEAKER_00"
    assert manifest_json["resolved"]["speaker_count"] == 1
    assert manifest_json["status"] == "succeeded"


def test_write_segments_srt(tmp_path: Path) -> None:
    output_path = tmp_path / "segments.zh.srt"
    write_segments_srt(
        [
            TranscriptionSegment(
                segment_id="seg-0001",
                start=0.0,
                end=1.0,
                text="你好",
                speaker_label="SPEAKER_00",
                language="zh",
                duration=1.0,
            )
        ],
        output_path,
    )
    content = output_path.read_text(encoding="utf-8")
    assert "00:00:00,000 --> 00:00:01,000" in content
    assert "[SPEAKER_00] 你好" in content


def test_resolve_faster_whisper_model_path_prefers_complete_local_cache(tmp_path: Path) -> None:
    hf_cache = tmp_path / "hub"
    model_cache = hf_cache / "models--Systran--faster-whisper-small"
    snapshot = model_cache / "snapshots" / "abc123"
    snapshot.mkdir(parents=True)
    (model_cache / "refs").mkdir()
    (model_cache / "refs" / "main").write_text("abc123", encoding="utf-8")

    for filename in ["model.bin", "config.json", "tokenizer.json", "vocabulary.txt"]:
        (snapshot / filename).write_text("cached", encoding="utf-8")

    assert resolve_faster_whisper_model_path("small", cache_dir=hf_cache) == str(snapshot)
