from __future__ import annotations

from pathlib import Path


def test_muxing_adapter_calls_mux_helper_and_copies_output(tmp_path: Path, monkeypatch) -> None:
    from translip.server.atomic_tools.adapters.muxing import MuxingAdapter

    video_path = tmp_path / "input" / "video_file" / "video.mp4"
    audio_path = tmp_path / "input" / "audio_file" / "audio.wav"
    video_path.parent.mkdir(parents=True, exist_ok=True)
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    video_path.write_bytes(b"video")
    audio_path.write_bytes(b"audio")
    output_dir = tmp_path / "output"

    def fake_mux_video_with_audio(**kwargs):
        output_path = kwargs["output_path"]
        output_path.write_bytes(b"muxed")
        return output_path

    monkeypatch.setattr(
        "translip.server.atomic_tools.adapters.muxing.mux_video_with_audio",
        fake_mux_video_with_audio,
    )

    result = MuxingAdapter().run(
        {
            "video_file_id": "video",
            "audio_file_id": "audio",
            "video_codec": "copy",
            "audio_codec": "aac",
            "audio_bitrate": "192k",
        },
        tmp_path / "input",
        output_dir,
        lambda *_args, **_kwargs: None,
    )

    assert (output_dir / "output.mp4").read_bytes() == b"muxed"
    assert result["output_file"] == "output.mp4"
