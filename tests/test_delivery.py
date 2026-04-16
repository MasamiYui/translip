from __future__ import annotations

import json
from pathlib import Path

from translip.types import ExportVideoRequest, MediaInfo
from translip.types import PipelineRequest


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"stub")


def _build_task_e_fixture(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    pipeline_root = tmp_path / "pipeline"
    input_video_path = tmp_path / "source.mp4"
    _touch(input_video_path)

    task_e_dir = pipeline_root / "task-e" / "voice"
    preview_mix_path = task_e_dir / "preview_mix.en.wav"
    dub_voice_path = task_e_dir / "dub_voice.en.wav"
    timeline_path = task_e_dir / "timeline.en.json"
    mix_report_path = task_e_dir / "mix_report.en.json"
    for path in [preview_mix_path, dub_voice_path, timeline_path, mix_report_path]:
        _touch(path)

    _write_json(
        task_e_dir / "task-e-manifest.json",
        {
            "request": {"target_lang": "en"},
            "resolved": {"target_lang": "en"},
            "artifacts": {
                "dub_voice": str(dub_voice_path),
                "preview_mix_wav": str(preview_mix_path),
                "timeline_json": str(timeline_path),
                "mix_report_json": str(mix_report_path),
            },
            "status": "succeeded",
            "error": None,
        },
    )
    _write_json(
        pipeline_root / "pipeline-manifest.json",
        {
            "request": {"input_path": str(input_video_path)},
            "status": "succeeded",
        },
    )
    return pipeline_root, input_video_path, preview_mix_path, dub_voice_path


def _fake_media_info(path: Path) -> MediaInfo:
    suffix = path.suffix.lower()
    media_type = "video" if suffix == ".mp4" else "audio"
    duration_sec = 12.0 if media_type == "video" else 11.5
    return MediaInfo(
        path=path,
        media_type=media_type,
        format_name="mov,mp4,m4a,3gp,3g2,mj2" if media_type == "video" else "wav",
        duration_sec=duration_sec,
        audio_stream_index=0,
        audio_stream_count=1,
        sample_rate=48_000 if media_type == "video" else 24_000,
        channels=2,
    )


def test_export_video_infers_inputs_from_pipeline_root_and_writes_delivery_artifacts(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from translip.delivery.runner import export_video

    pipeline_root, input_video_path, preview_mix_path, dub_voice_path = _build_task_e_fixture(tmp_path)
    mux_calls: list[dict[str, object]] = []

    def fake_mux_video_with_audio(
        *,
        input_video_path: Path,
        input_audio_path: Path,
        output_path: Path,
        video_codec: str,
        audio_codec: str,
        audio_bitrate: str | None,
        end_policy: str,
    ) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"video")
        mux_calls.append(
            {
                "input_video_path": input_video_path,
                "input_audio_path": input_audio_path,
                "output_path": output_path,
                "video_codec": video_codec,
                "audio_codec": audio_codec,
                "audio_bitrate": audio_bitrate,
                "end_policy": end_policy,
            }
        )
        return output_path

    monkeypatch.setattr("translip.delivery.runner.mux_video_with_audio", fake_mux_video_with_audio)
    monkeypatch.setattr("translip.delivery.runner.probe_media", _fake_media_info)

    result = export_video(
        ExportVideoRequest(
            pipeline_root=pipeline_root,
        )
    )

    assert result.artifacts.preview_video_path is not None
    assert result.artifacts.preview_video_path.exists()
    assert result.artifacts.dub_video_path is not None
    assert result.artifacts.dub_video_path.exists()
    assert result.artifacts.manifest_path.exists()
    assert result.artifacts.report_path.exists()

    assert result.request.input_video_path == input_video_path.resolve()
    assert result.request.task_e_dir == (pipeline_root / "task-e" / "voice").resolve()
    assert result.request.output_dir == (pipeline_root / "task-g" / "delivery").resolve()

    assert len(mux_calls) == 2
    assert mux_calls[0]["input_audio_path"] == preview_mix_path.resolve()
    assert mux_calls[1]["input_audio_path"] == dub_voice_path.resolve()
    assert mux_calls[0]["video_codec"] == "copy"
    assert mux_calls[0]["audio_codec"] == "aac"
    assert mux_calls[0]["end_policy"] == "trim_audio_to_video"

    manifest = json.loads(result.artifacts.manifest_path.read_text(encoding="utf-8"))
    report = json.loads(result.artifacts.report_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "succeeded"
    assert manifest["request"]["target_lang"] == "en"
    assert report["summary"]["exported_count"] == 2
    assert report["summary"]["failed_count"] == 0


def test_export_video_can_export_preview_only(tmp_path: Path, monkeypatch) -> None:
    from translip.delivery.runner import export_video

    pipeline_root, input_video_path, preview_mix_path, _dub_voice_path = _build_task_e_fixture(tmp_path)
    output_dir = tmp_path / "delivery"
    mux_calls: list[Path] = []

    def fake_mux_video_with_audio(
        *,
        input_video_path: Path,
        input_audio_path: Path,
        output_path: Path,
        video_codec: str,
        audio_codec: str,
        audio_bitrate: str | None,
        end_policy: str,
    ) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"preview-only")
        mux_calls.append(input_audio_path)
        return output_path

    monkeypatch.setattr("translip.delivery.runner.mux_video_with_audio", fake_mux_video_with_audio)
    monkeypatch.setattr("translip.delivery.runner.probe_media", _fake_media_info)

    result = export_video(
        ExportVideoRequest(
            input_video_path=input_video_path,
            task_e_dir=pipeline_root / "task-e" / "voice",
            output_dir=output_dir,
            target_lang="en",
            export_preview=True,
            export_dub=False,
        )
    )

    assert result.artifacts.preview_video_path is not None
    assert result.artifacts.preview_video_path.exists()
    assert result.artifacts.dub_video_path is None
    assert mux_calls == [preview_mix_path.resolve()]

    report = json.loads(result.artifacts.report_path.read_text(encoding="utf-8"))
    assert report["summary"]["exported_count"] == 1
    assert report["summary"]["requested_exports"] == ["preview"]


def test_resolve_delivery_inputs_prefers_clean_video_when_available(
    tmp_path: Path, monkeypatch
) -> None:
    from translip.delivery.runner import resolve_delivery_inputs

    request = PipelineRequest(
        input_path=tmp_path / "input.mp4",
        output_root=tmp_path / "out",
        template_id="asr-dub+ocr-subs+erase",
        delivery_policy={"video_source": "clean_if_available", "audio_source": "both", "subtitle_source": "both"},
    )
    request.input_path.write_text("video", encoding="utf-8")

    clean_video = request.output_root / "subtitle-erase" / "clean_video.mp4"
    clean_video.parent.mkdir(parents=True, exist_ok=True)
    clean_video.write_text("clean", encoding="utf-8")

    monkeypatch.setattr("translip.delivery.runner.probe_media", _fake_media_info)
    resolved = resolve_delivery_inputs(request)

    assert resolved.video_path == clean_video


def test_resolve_delivery_inputs_falls_back_to_original_video(tmp_path: Path) -> None:
    from translip.delivery.runner import resolve_delivery_inputs

    request = PipelineRequest(
        input_path=tmp_path / "input.mp4",
        output_root=tmp_path / "out",
        delivery_policy={"video_source": "clean_if_available", "audio_source": "original", "subtitle_source": "none"},
    )
    request.input_path.write_text("video", encoding="utf-8")

    resolved = resolve_delivery_inputs(request)

    assert resolved.video_path == request.input_path


def test_resolve_delivery_inputs_ignores_invalid_clean_video(
    tmp_path: Path, monkeypatch
) -> None:
    from translip.delivery.runner import resolve_delivery_inputs
    from translip.utils.ffmpeg import FFmpegError

    request = PipelineRequest(
        input_path=tmp_path / "input.mp4",
        output_root=tmp_path / "out",
        delivery_policy={"video_source": "clean_if_available", "audio_source": "both", "subtitle_source": "asr"},
    )
    request.input_path.write_text("video", encoding="utf-8")

    clean_video = request.output_root / "subtitle-erase" / "clean_video.mp4"
    clean_video.parent.mkdir(parents=True, exist_ok=True)
    clean_video.write_text("corrupt", encoding="utf-8")

    def fake_probe_media(path: Path) -> MediaInfo:
        if path == clean_video:
            raise FFmpegError("invalid clean video")
        return _fake_media_info(path)

    monkeypatch.setattr("translip.delivery.runner.probe_media", fake_probe_media)

    resolved = resolve_delivery_inputs(request)

    assert resolved.video_path == request.input_path
