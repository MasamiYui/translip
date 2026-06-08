from __future__ import annotations

import json
import sys
from pathlib import Path

from translip.orchestration.request import build_pipeline_request
from translip.orchestration.stages import resolve_stage_sequence
from translip.translation.backend import BackendSegmentOutput


def test_pipeline_request_merges_json_config_with_cli_override(tmp_path: Path) -> None:
    config_path = tmp_path / "pipeline.json"
    config_path.write_text(
        json.dumps(
            {
                "target_lang": "ja",
                "translation_backend": "local-m2m100",
                "write_status": False,
            }
        ),
        encoding="utf-8",
    )
    request = build_pipeline_request(
        {
            "config": str(config_path),
            "input": "sample.mp4",
            "output_root": "out",
            "target_lang": "en",
            "translation_backend": None,
            "write_status": True,
        }
    )
    assert request.target_lang == "en"
    assert request.translation_backend == "local-m2m100"
    assert request.write_status is True


def test_build_pipeline_request_keeps_template_and_delivery_policy() -> None:
    request = build_pipeline_request(
        {
            "input": "sample.mp4",
            "output_root": "out",
            "template": "asr-dub+ocr-subs",
            "subtitle_source": "both",
            "video_source": "clean_if_available",
            "audio_source": "both",
        }
    )

    assert request.template_id == "asr-dub+ocr-subs"
    assert request.delivery_policy["subtitle_source"] == "both"
    assert request.delivery_policy["video_source"] == "clean_if_available"


def test_build_pipeline_request_reads_erase_params() -> None:
    request = build_pipeline_request(
        {
            "input": "sample.mp4",
            "output_root": "out",
            "erase_backend": "lama",
            "erase_device": "cpu",
            "erase_max_load": 24,
        }
    )

    assert request.erase_backend == "lama"
    assert request.erase_device == "cpu"
    assert request.erase_max_load == 24
    # Sensible defaults remain when unset.
    assert request.erase_neighbor_stride == 5
    assert request.erase_reference_length == 10


def test_build_pipeline_request_defaults_to_moss_tts_nano_onnx() -> None:
    request = build_pipeline_request(
        {
            "input": "sample.mp4",
            "output_root": "out",
        }
    )

    assert request.tts_backend == "moss-tts-nano-onnx"


def test_build_pipeline_request_keeps_translation_batch_size() -> None:
    request = build_pipeline_request(
        {
            "input": "sample.mp4",
            "output_root": "out",
            "translation_batch_size": 2,
        }
    )

    assert request.translation_batch_size == 2


def test_build_pipeline_request_keeps_dubbing_speed_controls() -> None:
    request = build_pipeline_request(
        {
            "input": "sample.mp4",
            "output_root": "out",
            "dubbing_workers": 6,
            "dubbing_quality_check": " Duration-Only ",
        }
    )

    assert request.dubbing_workers == 6
    assert request.dubbing_quality_check == "duration-only"


def test_build_pipeline_request_keeps_transcription_advanced_controls() -> None:
    request = build_pipeline_request(
        {
            "input": "sample.mp4",
            "output_root": "out",
            "asr_model": "medium",
            "asr_backend": "funasr",
            "diarizer_backend": "pyannote",
            "enable_diarization": False,
            "vad_filter": False,
            "vad_min_silence_duration_ms": 650,
            "beam_size": 3,
            "best_of": 2,
            "temperature": 0.2,
            "condition_on_previous_text": True,
        }
    )

    assert request.asr_model == "medium"
    assert request.asr_backend == "funasr"
    assert request.diarizer_backend == "pyannote"
    assert request.enable_diarization is False
    assert request.vad_filter is False
    assert request.vad_min_silence_duration_ms == 650
    assert request.beam_size == 3
    assert request.best_of == 2
    assert request.temperature == 0.2
    assert request.condition_on_previous_text is True


def test_pipeline_request_normalized_preserves_transcription_backend_controls(tmp_path: Path) -> None:
    from translip.types import PipelineRequest

    request = PipelineRequest(
        input_path=tmp_path / "sample.mp4",
        output_root=tmp_path / "out",
        asr_backend="funasr",
        diarizer_backend="pyannote",
        enable_diarization=False,
    ).normalized()

    assert request.asr_backend == "funasr"
    assert request.diarizer_backend == "pyannote"
    assert request.enable_diarization is False


def test_pipeline_request_normalized_preserves_all_passthrough_fields(tmp_path: Path) -> None:
    from translip.types import PipelineRequest

    # Non-default values across the pass-through field spectrum. Under the old
    # hand-listed normalized() a field forgotten there would be silently reset to
    # its dataclass default; dataclasses.replace must carry every one verbatim.
    request = PipelineRequest(
        input_path=tmp_path / "sample.mp4",
        output_root=tmp_path / "out",
        config_path="~/cfg.json",
        target_lang="ja",
        translation_backend="deepseek",
        tts_backend="voxcpm2",
        api_model="deepseek-v4-pro",
        api_base_url="https://api.deepseek.com",
        output_sample_rate=44100,
        background_gain_db=-3.0,
        top_k=7,
        audio_stream_index=2,
        update_registry=True,
        erase_backend="lama",
        temperature=0,  # int -> coerced to float
    )
    normalized = request.normalized()

    for name, expected in {
        "target_lang": "ja",
        "translation_backend": "deepseek",
        "tts_backend": "voxcpm2",
        "api_model": "deepseek-v4-pro",
        "api_base_url": "https://api.deepseek.com",
        "output_sample_rate": 44100,
        "background_gain_db": -3.0,
        "top_k": 7,
        "audio_stream_index": 2,
        "update_registry": True,
        "erase_backend": "lama",
    }.items():
        assert getattr(normalized, name) == expected, name

    # path fields resolved to absolute, scalar coercion applied
    assert normalized.input_path.is_absolute()
    assert normalized.config_path is not None and normalized.config_path.is_absolute()
    assert isinstance(normalized.temperature, float)


def test_build_pipeline_request_rejects_invalid_dubbing_speed_controls() -> None:
    import pytest

    with pytest.raises(ValueError):
        build_pipeline_request(
            {
                "input": "sample.mp4",
                "output_root": "out",
                "dubbing_workers": 0,
            }
        )
    with pytest.raises(ValueError):
        build_pipeline_request(
            {
                "input": "sample.mp4",
                "output_root": "out",
                "dubbing_quality_check": "fast",
            }
        )


def test_build_pipeline_request_maps_dub_repair_config() -> None:
    request = build_pipeline_request(
        {
            "input": "sample.mp4",
            "output_root": "out",
            "dub_repair_enabled": True,
            "dub_repair_max_items": 12,
            "dub_repair_attempts_per_item": 5,
            "dub_repair_include_risk": True,
            "dub_repair_backend": ["moss-tts-nano-onnx", "qwen3tts"],
        }
    )

    assert request.dub_repair_enabled is True
    assert request.dub_repair_max_items == 12
    assert request.dub_repair_attempts_per_item == 5
    assert request.dub_repair_include_risk is True
    assert request.dub_repair_backends == ["moss-tts-nano-onnx", "qwen3tts"]


def test_task_e_command_passes_selected_repair_segments(tmp_path: Path) -> None:
    from translip.orchestration.commands import build_task_e_command
    from translip.types import PipelineRequest

    request = PipelineRequest(input_path=tmp_path / "sample.mp4", output_root=tmp_path / "out")
    selected_path = tmp_path / "out" / "task-d" / "voice" / "repair-run" / "selected_segments.en.json"
    command = build_task_e_command(
        request,
        task_d_reports=[tmp_path / "out" / "task-d" / "voice" / "spk_0000" / "speaker_segments.en.json"],
        selected_segments_path=selected_path,
    )

    assert "--selected-segments" in command
    assert str(selected_path) in command


def test_task_e_cache_payload_includes_render_mix_controls(tmp_path: Path) -> None:
    from translip.orchestration.runner import _stage_cache_payload
    from translip.types import PipelineRequest

    request = PipelineRequest(
        input_path=tmp_path / "sample.mp4",
        output_root=tmp_path / "out",
        background_gain_db=-12.0,
        window_ducking_db=-5.0,
        output_sample_rate=48000,
    )

    payload = _stage_cache_payload(request, "task-e")

    assert payload["background_gain_db"] == -12.0
    assert payload["window_ducking_db"] == -5.0
    assert payload["output_sample_rate"] == 48000


def test_task_d_command_passes_dubbing_speed_controls(tmp_path: Path) -> None:
    from translip.orchestration.commands import build_task_d_command
    from translip.types import PipelineRequest

    request = PipelineRequest(
        input_path=tmp_path / "sample.mp4",
        output_root=tmp_path / "out",
        dubbing_workers=6,
        dubbing_quality_check="duration-only",
    )
    command = build_task_d_command(request, speaker_id="spk_0000", segment_ids=None)

    assert "--dubbing-workers" in command
    assert "6" in command
    assert "--quality-check-mode" in command
    assert "duration-only" in command


def test_task_a_command_passes_transcription_advanced_controls(tmp_path: Path) -> None:
    from translip.orchestration.commands import build_task_a_command
    from translip.types import PipelineRequest

    request = PipelineRequest(
        input_path=tmp_path / "sample.mp4",
        output_root=tmp_path / "out",
        asr_model="medium",
        asr_backend="funasr",
        diarizer_backend="pyannote",
        enable_diarization=False,
        generate_srt=False,
        vad_filter=False,
        vad_min_silence_duration_ms=650,
        beam_size=3,
        best_of=2,
        temperature=0.2,
        condition_on_previous_text=True,
    )
    command = build_task_a_command(request)

    assert "--asr-model" in command
    assert "medium" in command
    assert "--asr-backend" in command
    assert "funasr" in command
    assert "--diarizer-backend" in command
    assert "pyannote" in command
    assert "--enable-diarization" not in command
    assert "--no-srt" in command
    assert "--no-vad-filter" in command
    assert "--vad-min-silence-duration-ms" in command
    assert "650" in command
    assert "--beam-size" in command
    assert "3" in command
    assert "--best-of" in command
    assert "2" in command
    assert "--temperature" in command
    assert "0.2" in command
    assert "--condition-on-previous-text" in command


def test_task_a_cache_payload_includes_transcription_backend_controls(tmp_path: Path) -> None:
    from translip.orchestration.runner import _stage_cache_payload
    from translip.types import PipelineRequest

    request = PipelineRequest(
        input_path=tmp_path / "sample.mp4",
        output_root=tmp_path / "out",
        asr_model="medium",
        asr_backend="funasr",
        diarizer_backend="pyannote",
        enable_diarization=False,
        generate_srt=False,
    )

    payload = _stage_cache_payload(request, "task-a")

    assert payload["asr_model"] == "medium"
    assert payload["asr_backend"] == "funasr"
    assert payload["diarizer_backend"] == "pyannote"
    assert payload["enable_diarization"] is False
    assert payload["generate_srt"] is False


def test_task_a_cache_key_tracks_stage1_voice(tmp_path: Path) -> None:
    """ARCH-4: task-a must recompute when the upstream stage1 voice stem changes."""
    from translip.orchestration.cache import compute_cache_key
    from translip.orchestration.commands import stage1_voice_path
    from translip.orchestration.runner import _stage_cache_payload
    from translip.types import PipelineRequest

    request = PipelineRequest(input_path=tmp_path / "in.mp4", output_root=tmp_path / "out")
    voice = stage1_voice_path(request)
    voice.parent.mkdir(parents=True, exist_ok=True)
    voice.write_bytes(b"AAAA")
    key_before = compute_cache_key(_stage_cache_payload(request, "task-a"))
    voice.write_bytes(b"BBBB")
    key_after = compute_cache_key(_stage_cache_payload(request, "task-a"))
    assert key_before != key_after


def test_task_d_cache_key_tracks_upstream_translation_and_profiles(tmp_path: Path) -> None:
    """ARCH-4: task-d must recompute when task-c translation or task-b profiles change."""
    from translip.orchestration.cache import compute_cache_key
    from translip.orchestration.commands import task_b_profiles_path, task_c_translation_path
    from translip.orchestration.runner import _stage_cache_payload
    from translip.types import PipelineRequest

    request = PipelineRequest(input_path=tmp_path / "in.mp4", output_root=tmp_path / "out")
    translation = task_c_translation_path(request)
    profiles = task_b_profiles_path(request)
    translation.parent.mkdir(parents=True, exist_ok=True)
    profiles.parent.mkdir(parents=True, exist_ok=True)
    translation.write_bytes(b"{}")
    profiles.write_bytes(b"{}")
    key_before = compute_cache_key(_stage_cache_payload(request, "task-d"))
    translation.write_bytes(b'{"changed": 1}')
    key_after_translation = compute_cache_key(_stage_cache_payload(request, "task-d"))
    assert key_after_translation != key_before
    profiles.write_bytes(b'{"changed": 2}')
    key_after_profiles = compute_cache_key(_stage_cache_payload(request, "task-d"))
    assert key_after_profiles != key_after_translation


def test_vad_max_segment_sec_is_plumbed_and_cached(tmp_path: Path) -> None:
    """ASR-8: the tunable reaches task-a's argv and changing it busts the cache."""
    from translip.orchestration.cache import compute_cache_key
    from translip.orchestration.commands import build_task_a_command
    from translip.orchestration.runner import _stage_cache_payload
    from translip.types import PipelineRequest

    request = PipelineRequest(
        input_path=tmp_path / "in.mp4", output_root=tmp_path / "out", vad_max_segment_sec=12.0
    )
    cmd = build_task_a_command(request)
    assert "--vad-max-segment-sec" in cmd
    assert "12.0" in cmd

    other = PipelineRequest(
        input_path=tmp_path / "in.mp4", output_root=tmp_path / "out", vad_max_segment_sec=30.0
    )
    assert compute_cache_key(_stage_cache_payload(request, "task-a")) != compute_cache_key(
        _stage_cache_payload(other, "task-a")
    )


def test_expected_speakers_is_plumbed_and_cached(tmp_path: Path) -> None:
    """ASR-3: the expected-speakers hint reaches task-a's argv and busts the cache."""
    from translip.orchestration.cache import compute_cache_key
    from translip.orchestration.commands import build_task_a_command
    from translip.orchestration.runner import _stage_cache_payload
    from translip.types import PipelineRequest

    request = PipelineRequest(
        input_path=tmp_path / "in.mp4", output_root=tmp_path / "out", expected_speakers=2
    )
    cmd = build_task_a_command(request)
    assert "--expected-speakers" in cmd
    assert cmd[cmd.index("--expected-speakers") + 1] == "2"

    other = PipelineRequest(
        input_path=tmp_path / "in.mp4", output_root=tmp_path / "out", expected_speakers=0
    )
    assert compute_cache_key(_stage_cache_payload(request, "task-a")) != compute_cache_key(
        _stage_cache_payload(other, "task-a")
    )


def test_cache_key_changes_with_cache_epoch(monkeypatch) -> None:
    """ARCH-5: bumping CACHE_EPOCH invalidates every cache key (release-level recompute)."""
    from translip.orchestration import cache

    payload = {"stage": "task-a", "x": 1}
    monkeypatch.setattr(cache, "CACHE_EPOCH", 1)
    key_v1 = cache.compute_cache_key(payload)
    monkeypatch.setattr(cache, "CACHE_EPOCH", 2)
    key_v2 = cache.compute_cache_key(payload)
    assert key_v1 != key_v2


def test_execute_task_e_writes_character_ledger_and_dub_benchmark(tmp_path: Path, monkeypatch) -> None:
    from translip.orchestration.commands import task_d_stage_manifest_path
    from translip.orchestration.monitor import PipelineMonitor
    from translip.orchestration.runner import execute_stage
    from translip.types import PipelineRequest

    request = PipelineRequest(input_path=tmp_path / "sample.mp4", output_root=tmp_path / "out")
    request.input_path.write_text("placeholder", encoding="utf-8")
    profiles_path = request.output_root / "task-b" / "voice" / "speaker_profiles.json"
    report_path = request.output_root / "task-d" / "voice" / "spk_0001" / "speaker_segments.en.json"
    profiles_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    profiles_path.write_text(
        json.dumps(
            {
                "profiles": [
                    {
                        "profile_id": "profile_0001",
                        "speaker_id": "spk_0001",
                        "source_label": "SPEAKER_01",
                        "reference_clips": [{"path": str(tmp_path / "missing-reference.wav")}],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    report_path.write_text(json.dumps({"speaker_id": "spk_0001", "segments": []}), encoding="utf-8")
    manifest_path = task_d_stage_manifest_path(request)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps({"reports": [str(report_path)]}), encoding="utf-8")

    def fake_run_stage_command(_command, *, log_path, on_stdout_line=None, env_overrides=None, should_cancel=None):
        mix_report_path = request.output_root / "task-e" / "voice" / "mix_report.en.json"
        mix_report_path.parent.mkdir(parents=True, exist_ok=True)
        mix_report_path.write_text(
            json.dumps(
                {
                    "stats": {
                        "placed_count": 1,
                        "skipped_count": 0,
                        "quality_summary": {
                            "total_count": 1,
                            "overall_status_counts": {"passed": 1},
                            "speaker_status_counts": {"passed": 1},
                            "intelligibility_status_counts": {"passed": 1},
                        },
                        "audible_coverage": {"failed_count": 0, "failed_segment_ids": []},
                    }
                }
            ),
            encoding="utf-8",
        )
        (request.output_root / "task-e" / "voice" / "dub_voice.en.wav").write_bytes(b"")
        (request.output_root / "task-e" / "voice" / "preview_mix.en.wav").write_bytes(b"")
        (request.output_root / "task-e" / "voice" / "timeline.en.json").write_text("{}", encoding="utf-8")
        (request.output_root / "task-e" / "voice" / "task-e-manifest.json").write_text("{}", encoding="utf-8")
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("ok", encoding="utf-8")

    monkeypatch.setattr("translip.orchestration.runner.run_stage_command", fake_run_stage_command)

    monitor = PipelineMonitor(job_id="job-1", status_path=tmp_path / "status.json", write_status=False)
    result = execute_stage("task-e", request, monitor=monitor)

    ledger_path = request.output_root / "task-d" / "voice" / "character-ledger" / "character_ledger.en.json"
    benchmark_path = request.output_root / "benchmark" / "voice" / "dub_benchmark.en.json"
    assert ledger_path.exists()
    assert benchmark_path.exists()
    assert str(ledger_path) in result["artifact_paths"]
    assert str(benchmark_path) in result["artifact_paths"]


def test_stage_sequence_respects_from_and_to() -> None:
    stages = resolve_stage_sequence("task-b", "task-d")
    assert stages == ["task-b", "task-c", "task-d"]


def test_pipeline_status_snapshot_contains_overall_and_stage_progress(tmp_path: Path) -> None:
    from translip.orchestration.monitor import PipelineMonitor

    status_path = tmp_path / "pipeline-status.json"
    monitor = PipelineMonitor(job_id="job-1", status_path=status_path, write_status=True)
    monitor.start_stage("task-d", current_step="speaker spk_0001 0/10")
    monitor.update_stage_progress("task-d", 25.0, "speaker spk_0001 2/10")
    payload = json.loads(status_path.read_text(encoding="utf-8"))
    assert payload["status"] == "running"
    assert payload["current_stage"] == "task-d"
    assert payload["overall_progress_percent"] > 0
    assert payload["stages"][0]["progress_percent"] == 25.0


def test_stage_cache_hits_when_manifest_and_artifacts_exist(tmp_path: Path) -> None:
    from translip.orchestration.cache import StageCacheSpec, is_stage_cache_hit

    manifest_path = tmp_path / "task-a-manifest.json"
    artifact_path = tmp_path / "segments.zh.json"
    manifest_path.write_text(json.dumps({"status": "succeeded"}), encoding="utf-8")
    artifact_path.write_text("{}", encoding="utf-8")
    stage = StageCacheSpec(
        stage_name="task-a",
        manifest_path=manifest_path,
        artifact_paths=[artifact_path],
        cache_key="abc",
        previous_cache_key="abc",
    )
    assert is_stage_cache_hit(stage) is True


def test_stage1_command_uses_python_module_cli(tmp_path: Path) -> None:
    from translip.orchestration.commands import build_stage1_command
    from translip.types import PipelineRequest

    request = PipelineRequest(input_path=tmp_path / "sample.mp4", output_root=tmp_path / "out")
    command = build_stage1_command(request)
    assert command[:3] == [sys.executable, "-m", "translip"]
    assert command[3] == "run"


def test_run_subtitle_erase_expands_ocr_detection_before_reuse(tmp_path: Path, monkeypatch) -> None:
    from translip.orchestration.erase_bridge import run_subtitle_erase
    from translip.types import PipelineRequest

    request = PipelineRequest(
        input_path=tmp_path / "sample.mp4",
        output_root=tmp_path / "out",
        erase_event_lead_frames=4,
        erase_event_trail_frames=11,
    )
    request.input_path.write_bytes(b"\x00" * 16)
    detection_path = request.output_root / "ocr-detect" / "detection.json"
    detection_path.parent.mkdir(parents=True)
    detection_path.write_text(
        json.dumps(
            {
                "video": {"fps": 20.0, "total_frames": 60, "width": 960, "height": 416, "duration": 3.0},
                "mode": "auto",
                "events": [
                    {
                        "index": 1,
                        "start_time": 0.5,
                        "end_time": 1.0,
                        "start_frame": 10,
                        "end_frame": 20,
                        "text": "测试字幕",
                        "confidence": 0.9,
                        "box": [100, 300, 340, 360],
                        "polygon": None,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    captured: dict[str, object] = {}

    def fake_run_stage_command(command, *, log_path, on_stdout_line=None, env_overrides=None, should_cancel=None):
        captured["command"] = list(command)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("ok", encoding="utf-8")

    monkeypatch.setattr("translip.orchestration.erase_bridge.run_stage_command", fake_run_stage_command)

    run_subtitle_erase(request, log_path=request.output_root / "logs" / "subtitle-erase.log")

    command = captured["command"]
    assert isinstance(command, list)
    assert "translip.erase.extract" in command
    assert "subtitle_eraser.cli" not in command
    reuse_path = Path(command[command.index("--detection") + 1])
    assert reuse_path != detection_path
    expanded = json.loads(reuse_path.read_text(encoding="utf-8"))
    assert expanded["events"][0]["start_frame"] == 6
    assert expanded["events"][0]["end_frame"] == 31
    assert expanded["events"][0]["start_time"] == 6 / 20.0
    assert expanded["events"][0]["end_time"] == 31 / 20.0


def test_run_pipeline_aborts_when_should_cancel_returns_true(tmp_path: Path) -> None:
    """ARCH-8: a set cancel flag stops the pipeline before running any stage and
    propagates StageSubprocessCancelled instead of silently continuing."""
    import pytest

    from translip.orchestration.runner import run_pipeline
    from translip.orchestration.subprocess_runner import StageSubprocessCancelled
    from translip.types import PipelineRequest

    input_path = tmp_path / "in.mp4"
    input_path.write_bytes(b"fake")
    request = PipelineRequest(
        input_path=input_path,
        output_root=tmp_path / "out",
        run_from_stage="stage1",
        run_to_stage="task-e",
        reuse_existing=False,
    )

    executed: list[str] = []

    def stage_executor(node_name, request, *, monitor):
        executed.append(node_name)
        return {"manifest_path": "", "artifact_paths": [], "log_path": ""}

    with pytest.raises(StageSubprocessCancelled):
        run_pipeline(request, stage_executor=stage_executor, should_cancel=lambda: True)

    assert executed == []


def test_effective_task_a_segments_prefers_speaker_corrected_segments(tmp_path: Path) -> None:
    from translip.orchestration.commands import (
        effective_task_a_segments_path,
        task_a_corrected_segments_path,
        task_a_speaker_corrected_segments_path,
        task_a_segments_path,
    )
    from translip.types import PipelineRequest

    request = PipelineRequest(input_path=tmp_path / "sample.mp4", output_root=tmp_path / "out")
    original = task_a_segments_path(request)
    corrected = task_a_corrected_segments_path(request)
    speaker_corrected = task_a_speaker_corrected_segments_path(request)
    original.parent.mkdir(parents=True)
    original.write_text("{}", encoding="utf-8")
    corrected.parent.mkdir(parents=True)
    corrected.write_text("{}", encoding="utf-8")
    speaker_corrected.write_text("{}", encoding="utf-8")

    assert effective_task_a_segments_path(request) == speaker_corrected


def test_effective_task_a_segments_prefers_text_corrected_before_original(tmp_path: Path) -> None:
    from translip.orchestration.commands import (
        effective_task_a_segments_path,
        task_a_corrected_segments_path,
        task_a_segments_path,
    )
    from translip.types import PipelineRequest

    request = PipelineRequest(input_path=tmp_path / "sample.mp4", output_root=tmp_path / "out")
    original = task_a_segments_path(request)
    corrected = task_a_corrected_segments_path(request)
    original.parent.mkdir(parents=True)
    original.write_text("{}", encoding="utf-8")
    corrected.parent.mkdir(parents=True)
    corrected.write_text("{}", encoding="utf-8")

    assert effective_task_a_segments_path(request) == corrected


def test_effective_task_a_segments_falls_back_to_original(tmp_path: Path) -> None:
    from translip.orchestration.commands import effective_task_a_segments_path, task_a_segments_path
    from translip.types import PipelineRequest

    request = PipelineRequest(input_path=tmp_path / "sample.mp4", output_root=tmp_path / "out")
    original = task_a_segments_path(request)

    assert effective_task_a_segments_path(request) == original


def test_run_pipeline_writes_manifest_report_and_status(tmp_path: Path, monkeypatch) -> None:
    from translip.orchestration.runner import run_pipeline
    from translip.types import PipelineRequest

    request = PipelineRequest(
        input_path=tmp_path / "sample.mp4",
        output_root=tmp_path / "pipeline-out",
        run_to_stage="task-c",
        write_status=True,
    )
    request.input_path.write_text("placeholder", encoding="utf-8")

    calls: list[str] = []

    def fake_stage_executor(stage_name: str, *_args, **_kwargs):
        calls.append(stage_name)
        stage_dir = request.output_root / stage_name
        stage_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = stage_dir / f"{stage_name}.json"
        manifest_path.write_text(json.dumps({"status": "succeeded"}), encoding="utf-8")
        return {"manifest_path": str(manifest_path), "artifact_paths": [str(manifest_path)]}

    monkeypatch.setattr("translip.orchestration.runner.execute_stage", fake_stage_executor)

    result = run_pipeline(request)

    assert calls == ["stage1", "task-a", "task-b", "task-c"]
    assert result.manifest_path.exists()
    assert result.report_path.exists()
    assert result.status_path.exists()


def test_pipeline_runner_marks_cached_stage_when_manifest_reusable(tmp_path: Path, monkeypatch) -> None:
    from translip.orchestration.runner import run_pipeline
    from translip.types import PipelineRequest

    input_path = tmp_path / "sample.mp4"
    input_path.write_text("placeholder", encoding="utf-8")
    output_root = tmp_path / "pipeline-out"
    manifest_path = output_root / "task-a" / "voice" / "task-a-manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps({"status": "succeeded"}), encoding="utf-8")
    artifact_path = output_root / "task-a" / "voice" / "segments.zh.json"
    artifact_path.write_text("{}", encoding="utf-8")
    request = PipelineRequest(
        input_path=input_path,
        output_root=output_root,
        run_from_stage="task-a",
        run_to_stage="task-a",
    )

    executed: list[str] = []

    def fake_stage_executor(stage_name: str, *_args, **_kwargs):
        executed.append(stage_name)
        return {"manifest_path": str(manifest_path), "artifact_paths": [str(artifact_path)]}

    monkeypatch.setattr("translip.orchestration.runner.execute_stage", fake_stage_executor)

    result = run_pipeline(request)

    assert executed == []
    payload = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert payload["stages"][0]["status"] == "cached"


def test_task_g_cache_requires_requested_delivery_outputs(tmp_path: Path, monkeypatch) -> None:
    from translip.orchestration.runner import run_pipeline
    from translip.types import PipelineRequest

    input_path = tmp_path / "sample.mp4"
    input_path.write_text("placeholder", encoding="utf-8")
    output_root = tmp_path / "pipeline-out"
    task_g_dir = output_root / "task-g"
    task_g_dir.mkdir(parents=True)
    (task_g_dir / "delivery-manifest.json").write_text(
        json.dumps({"status": "succeeded", "request": {"export_preview": True, "export_dub": False}}),
        encoding="utf-8",
    )
    (task_g_dir / "delivery-report.json").write_text(json.dumps({"status": "succeeded"}), encoding="utf-8")

    request = PipelineRequest(
        input_path=input_path,
        output_root=output_root,
        run_from_stage="task-g",
        run_to_stage="task-g",
        delivery_policy={"video_source": "original", "audio_source": "both", "subtitle_source": "asr"},
    )

    monkeypatch.setattr(
        "translip.orchestration.runner.resolve_template_plan",
        lambda template_id: type(
            "Plan",
            (),
            {
                "template_id": template_id,
                "node_order": ["task-g"],
                "nodes": {"task-g": type("Node", (), {"required": True})()},
            },
        )(),
    )

    executed: list[str] = []

    def fake_execute_node(stage_name: str, *_args, **_kwargs):
        executed.append(stage_name)
        final_dub = task_g_dir / "final-dub" / "final_dub.en.mp4"
        final_dub.parent.mkdir(parents=True)
        final_dub.write_bytes(b"dub")
        return {
            "manifest_path": str(task_g_dir / "delivery-manifest.json"),
            "artifact_paths": [str(task_g_dir / "delivery-manifest.json"), str(final_dub)],
        }

    monkeypatch.setattr("translip.orchestration.runner.execute_node", fake_execute_node)

    result = run_pipeline(request)

    assert executed == ["task-g"]
    payload = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert payload["stages"][0]["status"] == "succeeded"
    assert payload["stages"][0]["cache_hit"] is False


def test_task_g_cache_treats_preview_audio_source_as_preview_mix(tmp_path: Path, monkeypatch) -> None:
    from translip.orchestration.runner import run_pipeline
    from translip.types import PipelineRequest

    input_path = tmp_path / "sample.mp4"
    input_path.write_text("placeholder", encoding="utf-8")
    output_root = tmp_path / "pipeline-out"
    task_g_dir = output_root / "task-g"
    task_g_dir.mkdir(parents=True)
    (task_g_dir / "delivery-manifest.json").write_text(json.dumps({"status": "succeeded"}), encoding="utf-8")
    (task_g_dir / "delivery-report.json").write_text(json.dumps({"status": "succeeded"}), encoding="utf-8")

    request = PipelineRequest(
        input_path=input_path,
        output_root=output_root,
        run_from_stage="task-g",
        run_to_stage="task-g",
        delivery_policy={"video_source": "original", "audio_source": "preview", "subtitle_source": "asr"},
    )

    monkeypatch.setattr(
        "translip.orchestration.runner.resolve_template_plan",
        lambda template_id: type(
            "Plan",
            (),
            {
                "template_id": template_id,
                "node_order": ["task-g"],
                "nodes": {"task-g": type("Node", (), {"required": True})()},
            },
        )(),
    )

    executed: list[str] = []

    def fake_execute_node(stage_name: str, *_args, **_kwargs):
        executed.append(stage_name)
        final_preview = task_g_dir / "final-preview" / "final_preview.en.mp4"
        final_preview.parent.mkdir(parents=True)
        final_preview.write_bytes(b"preview")
        return {
            "manifest_path": str(task_g_dir / "delivery-manifest.json"),
            "artifact_paths": [str(task_g_dir / "delivery-manifest.json"), str(final_preview)],
        }

    monkeypatch.setattr("translip.orchestration.runner.execute_node", fake_execute_node)

    result = run_pipeline(request)

    assert executed == ["task-g"]
    payload = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert payload["stages"][0]["status"] == "succeeded"
    assert payload["stages"][0]["cache_hit"] is False


def test_task_g_cache_rejects_manifest_that_omits_requested_dub_export(tmp_path: Path, monkeypatch) -> None:
    from translip.orchestration.runner import run_pipeline
    from translip.types import PipelineRequest

    input_path = tmp_path / "sample.mp4"
    input_path.write_text("placeholder", encoding="utf-8")
    output_root = tmp_path / "pipeline-out"
    task_g_dir = output_root / "task-g"
    task_g_dir.mkdir(parents=True)
    final_preview = task_g_dir / "final-preview" / "final_preview.en.mp4"
    final_preview.parent.mkdir(parents=True)
    final_preview.write_bytes(b"preview")
    stale_dub = task_g_dir / "final-dub" / "final_dub.en.mp4"
    stale_dub.parent.mkdir(parents=True)
    stale_dub.write_bytes(b"stale dub")
    (task_g_dir / "delivery-manifest.json").write_text(
        json.dumps(
            {
                "status": "succeeded",
                "request": {"export_preview": True, "export_dub": False},
                "artifacts": {"final_preview_video": str(final_preview), "final_dub_video": None},
            }
        ),
        encoding="utf-8",
    )
    (task_g_dir / "delivery-report.json").write_text(json.dumps({"status": "succeeded"}), encoding="utf-8")

    request = PipelineRequest(
        input_path=input_path,
        output_root=output_root,
        run_from_stage="task-g",
        run_to_stage="task-g",
        delivery_policy={"video_source": "original", "audio_source": "both", "subtitle_source": "asr"},
    )

    monkeypatch.setattr(
        "translip.orchestration.runner.resolve_template_plan",
        lambda template_id: type(
            "Plan",
            (),
            {
                "template_id": template_id,
                "node_order": ["task-g"],
                "nodes": {"task-g": type("Node", (), {"required": True})()},
            },
        )(),
    )

    executed: list[str] = []

    def fake_execute_node(stage_name: str, *_args, **_kwargs):
        executed.append(stage_name)
        return {
            "manifest_path": str(task_g_dir / "delivery-manifest.json"),
            "artifact_paths": [str(task_g_dir / "delivery-manifest.json"), str(stale_dub)],
        }

    monkeypatch.setattr("translip.orchestration.runner.execute_node", fake_execute_node)

    result = run_pipeline(request)

    assert executed == ["task-g"]
    payload = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert payload["stages"][0]["status"] == "succeeded"
    assert payload["stages"][0]["cache_hit"] is False


def test_run_pipeline_executes_nodes_from_template_plan(tmp_path: Path, monkeypatch) -> None:
    from translip.orchestration.runner import run_pipeline
    from translip.types import PipelineRequest

    input_path = tmp_path / "sample.mp4"
    input_path.write_text("placeholder", encoding="utf-8")
    request = PipelineRequest(
        input_path=input_path,
        output_root=tmp_path / "workflow-out",
        template_id="asr-dub-basic",
    )

    monkeypatch.setattr(
        "translip.orchestration.runner.resolve_template_plan",
        lambda template_id: type(
            "Plan",
            (),
            {
                "template_id": template_id,
                "node_order": ["stage1", "task-a", "task-b"],
                "nodes": {
                    "stage1": type("Node", (), {"required": True})(),
                    "task-a": type("Node", (), {"required": True})(),
                    "task-b": type("Node", (), {"required": True})(),
                },
            },
        )(),
    )

    calls: list[str] = []

    def fake_execute(node_name: str, *_args, **_kwargs):
        calls.append(node_name)
        node_dir = request.output_root / node_name
        node_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = node_dir / f"{node_name}.json"
        manifest_path.write_text(json.dumps({"status": "succeeded"}), encoding="utf-8")
        return {"manifest_path": str(manifest_path), "artifact_paths": [str(manifest_path)]}

    monkeypatch.setattr("translip.orchestration.runner.execute_node", fake_execute)

    result = run_pipeline(request)

    assert calls == ["stage1", "task-a", "task-b"]
    payload = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert payload["status"] == "succeeded"


def test_run_pipeline_executes_asr_ocr_correction_before_task_b(tmp_path: Path, monkeypatch) -> None:
    from translip.orchestration.runner import run_pipeline
    from translip.types import PipelineRequest

    input_path = tmp_path / "sample.mp4"
    input_path.write_text("placeholder", encoding="utf-8")
    request = PipelineRequest(
        input_path=input_path,
        output_root=tmp_path / "workflow-out",
        template_id="asr-dub+ocr-subs",
        run_to_stage="task-b",
    )

    calls: list[str] = []

    def fake_execute(node_name: str, *_args, **_kwargs):
        calls.append(node_name)
        node_dir = request.output_root / node_name / "voice"
        node_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = node_dir / f"{node_name}.json"
        manifest_path.write_text(json.dumps({"status": "succeeded"}), encoding="utf-8")
        return {"manifest_path": str(manifest_path), "artifact_paths": [str(manifest_path)]}

    monkeypatch.setattr("translip.orchestration.runner.execute_node", fake_execute)

    run_pipeline(request)

    assert calls == ["stage1", "ocr-detect", "task-a", "asr-ocr-correct", "task-b"]


def test_run_pipeline_marks_partial_success_when_optional_node_fails(tmp_path: Path, monkeypatch) -> None:
    from translip.orchestration.runner import run_pipeline
    from translip.types import PipelineRequest

    input_path = tmp_path / "sample.mp4"
    input_path.write_text("placeholder", encoding="utf-8")
    request = PipelineRequest(
        input_path=input_path,
        output_root=tmp_path / "workflow-out",
        template_id="asr-dub+ocr-subs+erase",
        run_to_stage="task-g",
    )

    monkeypatch.setattr(
        "translip.orchestration.runner.resolve_template_plan",
        lambda _template_id: type(
            "Plan",
            (),
            {
                "template_id": "asr-dub+ocr-subs+erase",
                "node_order": ["stage1", "ocr-detect", "subtitle-erase", "task-g"],
                "nodes": {
                    "stage1": type("Node", (), {"required": True})(),
                    "ocr-detect": type("Node", (), {"required": True})(),
                    "subtitle-erase": type("Node", (), {"required": False})(),
                    "task-g": type("Node", (), {"required": True})(),
                },
            },
        )(),
    )

    def fake_execute(node_name: str, *_args, **_kwargs):
        if node_name == "subtitle-erase":
            raise RuntimeError("erase failed")
        node_dir = request.output_root / node_name
        node_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = node_dir / f"{node_name}.json"
        manifest_path.write_text(json.dumps({"status": "succeeded"}), encoding="utf-8")
        return {"manifest_path": str(manifest_path), "artifact_paths": [str(manifest_path)]}

    monkeypatch.setattr("translip.orchestration.runner.execute_node", fake_execute)

    result = run_pipeline(request)

    payload = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert payload["status"] == "partial_success"


def test_translate_ocr_events_writes_json_and_srt(tmp_path: Path) -> None:
    from translip.subtitles.runner import translate_ocr_events

    class FakeBackend:
        backend_name = "fake"
        resolved_model = "fake-model"
        resolved_device = "cpu"

        def translate_batch(self, *, items, source_lang: str, target_lang: str):
            return [
                BackendSegmentOutput(segment_id=item.segment_id, target_text=f"{target_lang}:{item.source_text}")
                for item in items
            ]

    events_path = tmp_path / "ocr_events.json"
    events_path.write_text(
        json.dumps(
            {
                "events": [
                    {
                        "event_id": "evt-1",
                        "start": 0.0,
                        "end": 1.5,
                        "text": "你好",
                        "language": "zh",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = translate_ocr_events(
        events_path=events_path,
        output_dir=tmp_path / "ocr-translate",
        target_lang="en",
        backend_name="local-m2m100",
        backend_override=FakeBackend(),
    )

    assert result.json_path.exists()
    assert result.srt_path.exists()
    payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert payload["events"][0]["translated_text"] == "en:你好"


def test_translate_ocr_events_uses_batches_and_reports_progress(tmp_path: Path) -> None:
    from translip.subtitles.runner import translate_ocr_events

    class FakeBackend:
        backend_name = "fake"
        resolved_model = "fake-model"
        resolved_device = "cpu"

        def __init__(self) -> None:
            self.batch_sizes: list[int] = []

        def translate_batch(self, *, items, source_lang: str, target_lang: str):
            self.batch_sizes.append(len(items))
            return [
                BackendSegmentOutput(segment_id=item.segment_id, target_text=f"{target_lang}:{item.source_text}")
                for item in items
            ]

    events = [
        {
            "event_id": f"evt-{index}",
            "start": float(index),
            "end": float(index) + 1.0,
            "text": f"字幕{index}",
            "language": "zh",
        }
        for index in range(5)
    ]
    events_path = tmp_path / "ocr_events.json"
    events_path.write_text(json.dumps({"events": events}), encoding="utf-8")
    backend = FakeBackend()
    progress: list[tuple[int, int]] = []

    result = translate_ocr_events(
        events_path=events_path,
        output_dir=tmp_path / "ocr-translate",
        target_lang="en",
        backend_name="local-m2m100",
        backend_override=backend,
        batch_size=2,
        progress_callback=lambda completed, total: progress.append((completed, total)),
    )

    assert backend.batch_sizes == [2, 2, 1]
    assert progress == [(2, 5), (4, 5), (5, 5)]
    payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert [event["translated_text"] for event in payload["events"]] == [
        "en:字幕0",
        "en:字幕1",
        "en:字幕2",
        "en:字幕3",
        "en:字幕4",
    ]
