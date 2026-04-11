import json
from pathlib import Path

from video_voice_separate.pipeline.manifest import build_manifest
from video_voice_separate.types import MediaInfo, RouteDecision, SeparationRequest


def test_manifest_shape(tmp_path: Path) -> None:
    request = SeparationRequest(input_path="input.wav")
    media_info = MediaInfo(
        path=Path("/tmp/input.wav"),
        media_type="audio",
        format_name="wav",
        duration_sec=1.0,
        audio_stream_index=0,
        audio_stream_count=1,
        sample_rate=44100,
        channels=2,
    )
    route = RouteDecision(route="music", reason="manual-mode", metrics={})
    manifest = build_manifest(
        request=request.normalized(),
        media_info=media_info,
        route=route,
        voice_path=tmp_path / "voice.wav",
        background_path=tmp_path / "background.wav",
        started_at="2026-04-11T20:00:00+08:00",
        finished_at="2026-04-11T20:00:01+08:00",
        elapsed_sec=1.0,
        backends={"music_backend": "demucs", "dialogue_backend": "cdx23"},
    )
    payload = json.loads(json.dumps(manifest))
    assert payload["status"] == "succeeded"
    assert payload["resolved"]["route"] == "music"
