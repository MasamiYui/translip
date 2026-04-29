from __future__ import annotations

import sys
from pathlib import Path

from ..types import PipelineRequest
from ..utils.files import slugify_filename


def _cli_prefix() -> list[str]:
    return [sys.executable, "-m", "translip"]


def stage1_bundle_dir(request: PipelineRequest) -> Path:
    return request.output_root / "stage1" / slugify_filename(request.input_path)


def stage1_voice_path(request: PipelineRequest) -> Path:
    return stage1_bundle_dir(request) / f"voice.{request.stage1_output_format}"


def stage1_background_path(request: PipelineRequest) -> Path:
    return stage1_bundle_dir(request) / f"background.{request.stage1_output_format}"


def stage1_manifest_path(request: PipelineRequest) -> Path:
    return stage1_bundle_dir(request) / "manifest.json"


def task_a_bundle_dir(request: PipelineRequest) -> Path:
    return request.output_root / "task-a" / "voice"


def task_a_segments_path(request: PipelineRequest) -> Path:
    return task_a_bundle_dir(request) / "segments.zh.json"


def task_a_correction_bundle_dir(request: PipelineRequest) -> Path:
    return request.output_root / "asr-ocr-correct" / "voice"


def task_a_corrected_segments_path(request: PipelineRequest) -> Path:
    return task_a_correction_bundle_dir(request) / "segments.zh.corrected.json"


def task_a_corrected_srt_path(request: PipelineRequest) -> Path:
    return task_a_correction_bundle_dir(request) / "segments.zh.corrected.srt"


def task_a_speaker_corrected_segments_path(request: PipelineRequest) -> Path:
    return task_a_correction_bundle_dir(request) / "segments.zh.speaker-corrected.json"


def task_a_speaker_corrected_srt_path(request: PipelineRequest) -> Path:
    return task_a_correction_bundle_dir(request) / "segments.zh.speaker-corrected.srt"


def task_a_correction_report_path(request: PipelineRequest) -> Path:
    return task_a_correction_bundle_dir(request) / "correction-report.json"


def task_a_correction_manifest_path(request: PipelineRequest) -> Path:
    return task_a_correction_bundle_dir(request) / "correction-manifest.json"


def effective_task_a_segments_path(request: PipelineRequest) -> Path:
    speaker_corrected = task_a_speaker_corrected_segments_path(request)
    if speaker_corrected.exists():
        return speaker_corrected
    corrected = task_a_corrected_segments_path(request)
    return corrected if corrected.exists() else task_a_segments_path(request)


def task_a_manifest_path(request: PipelineRequest) -> Path:
    return task_a_bundle_dir(request) / "task-a-manifest.json"


def task_b_bundle_dir(request: PipelineRequest) -> Path:
    return request.output_root / "task-b" / "voice"


def task_b_profiles_path(request: PipelineRequest) -> Path:
    return task_b_bundle_dir(request) / "speaker_profiles.json"


def task_b_matches_path(request: PipelineRequest) -> Path:
    return task_b_bundle_dir(request) / "speaker_matches.json"


def task_b_registry_path(request: PipelineRequest) -> Path:
    if request.registry_path is not None:
        return request.registry_path
    return request.output_root / "task-b" / "registry" / "speaker_registry.json"


def task_b_manifest_path(request: PipelineRequest) -> Path:
    return task_b_bundle_dir(request) / "task-b-manifest.json"


def task_b_voice_bank_path(request: PipelineRequest) -> Path:
    return task_b_bundle_dir(request) / f"voice_bank.{request.target_lang}.json"


def task_c_bundle_dir(request: PipelineRequest) -> Path:
    return request.output_root / "task-c" / "voice"


def task_c_translation_path(request: PipelineRequest) -> Path:
    return task_c_bundle_dir(request) / f"translation.{request.target_lang}.json"


def task_c_manifest_path(request: PipelineRequest) -> Path:
    return task_c_bundle_dir(request) / "task-c-manifest.json"


def task_d_bundle_dir(request: PipelineRequest) -> Path:
    return request.output_root / "task-d"


def task_d_voice_dir(request: PipelineRequest) -> Path:
    return task_d_bundle_dir(request) / "voice"


def task_d_stage_manifest_path(request: PipelineRequest) -> Path:
    return task_d_bundle_dir(request) / "task-d-stage-manifest.json"


def task_d_report_path(request: PipelineRequest, speaker_id: str) -> Path:
    return task_d_voice_dir(request) / speaker_id / f"speaker_segments.{request.target_lang}.json"


def task_e_bundle_dir(request: PipelineRequest) -> Path:
    return request.output_root / "task-e" / "voice"


def task_e_dub_voice_path(request: PipelineRequest) -> Path:
    return task_e_bundle_dir(request) / f"dub_voice.{request.target_lang}.wav"


def task_e_preview_mix_path(request: PipelineRequest) -> Path:
    return task_e_bundle_dir(request) / f"preview_mix.{request.target_lang}.wav"


def task_e_timeline_path(request: PipelineRequest) -> Path:
    return task_e_bundle_dir(request) / f"timeline.{request.target_lang}.json"


def task_e_mix_report_path(request: PipelineRequest) -> Path:
    return task_e_bundle_dir(request) / f"mix_report.{request.target_lang}.json"


def task_e_manifest_path(request: PipelineRequest) -> Path:
    return task_e_bundle_dir(request) / "task-e-manifest.json"


def build_stage1_command(request: PipelineRequest) -> list[str]:
    return [
        *_cli_prefix(),
        "run",
        "--input",
        str(request.input_path),
        "--mode",
        request.separation_mode,
        "--output-dir",
        str(request.output_root / "stage1"),
        "--quality",
        request.separation_quality,
        "--output-format",
        request.stage1_output_format,
        "--device",
        request.device,
        "--audio-stream-index",
        str(request.audio_stream_index),
    ]


def build_task_a_command(request: PipelineRequest) -> list[str]:
    return [
        *_cli_prefix(),
        "transcribe",
        "--input",
        str(stage1_voice_path(request)),
        "--output-dir",
        str(request.output_root / "task-a"),
        "--language",
        request.transcription_language,
        "--asr-model",
        request.asr_model,
        "--device",
        request.device,
    ]


def build_task_b_command(request: PipelineRequest) -> list[str]:
    command = [
        *_cli_prefix(),
        "build-speaker-registry",
        "--segments",
        str(effective_task_a_segments_path(request)),
        "--audio",
        str(stage1_voice_path(request)),
        "--output-dir",
        str(request.output_root / "task-b"),
        "--registry",
        str(task_b_registry_path(request)),
        "--device",
        request.device,
        "--top-k",
        str(request.top_k),
    ]
    if request.update_registry:
        command.append("--update-registry")
    return command


def build_task_c_command(request: PipelineRequest) -> list[str]:
    command = [
        *_cli_prefix(),
        "translate-script",
        "--segments",
        str(effective_task_a_segments_path(request)),
        "--profiles",
        str(task_b_profiles_path(request)),
        "--output-dir",
        str(request.output_root / "task-c"),
        "--target-lang",
        request.target_lang,
        "--backend",
        request.translation_backend,
        "--batch-size",
        str(request.translation_batch_size),
        "--device",
        request.device,
        "--condense-mode",
        request.condense_mode,
    ]
    if request.glossary_path is not None:
        command.extend(["--glossary", str(request.glossary_path)])
    if request.api_model:
        command.extend(["--api-model", request.api_model])
    if request.api_base_url:
        command.extend(["--api-base-url", request.api_base_url])
    return command


def build_task_d_command(request: PipelineRequest, *, speaker_id: str, segment_ids: list[str] | None) -> list[str]:
    command = [
        *_cli_prefix(),
        "synthesize-speaker",
        "--translation",
        str(task_c_translation_path(request)),
        "--profiles",
        str(task_b_profiles_path(request)),
        "--speaker-id",
        speaker_id,
        "--output-dir",
        str(task_d_bundle_dir(request)),
        "--backend",
        request.tts_backend,
        "--device",
        request.device,
    ]
    voice_bank_path = task_b_voice_bank_path(request)
    if voice_bank_path.exists():
        command.extend(["--voice-bank", str(voice_bank_path)])
    if segment_ids:
        for segment_id in segment_ids:
            command.extend(["--segment-id", segment_id])
    return command


def build_task_e_command(request: PipelineRequest, *, task_d_reports: list[Path]) -> list[str]:
    command = [
        *_cli_prefix(),
        "render-dub",
        "--background",
        str(stage1_background_path(request)),
        "--segments",
        str(effective_task_a_segments_path(request)),
        "--translation",
        str(task_c_translation_path(request)),
        "--output-dir",
        str(request.output_root / "task-e"),
        "--target-lang",
        request.target_lang,
        "--fit-policy",
        request.fit_policy,
        "--fit-backend",
        request.fit_backend,
        "--mix-profile",
        request.mix_profile,
        "--ducking-mode",
        request.ducking_mode,
        "--output-sample-rate",
        str(request.output_sample_rate),
        "--background-gain-db",
        str(request.background_gain_db),
        "--window-ducking-db",
        str(request.window_ducking_db),
        "--max-compress-ratio",
        str(request.max_compress_ratio),
        "--preview-format",
        request.preview_format,
    ]
    for report_path in task_d_reports:
        command.extend(["--task-d-report", str(report_path)])
    return command


def build_asr_ocr_correction_command(request: PipelineRequest) -> list[str]:
    config = request.transcription_correction
    command = [
        *_cli_prefix(),
        "correct-asr-with-ocr",
        "--segments",
        str(task_a_segments_path(request)),
        "--ocr-events",
        str(request.output_root / "ocr-detect" / "ocr_events.json"),
        "--output-dir",
        str(request.output_root / "asr-ocr-correct"),
        "--preset",
        str(config.get("preset", "standard")),
    ]
    if config.get("enabled", True) is False:
        command.append("--disabled")
    return command


__all__ = [
    "build_asr_ocr_correction_command",
    "build_stage1_command",
    "build_task_a_command",
    "build_task_b_command",
    "build_task_c_command",
    "build_task_d_command",
    "build_task_e_command",
    "stage1_background_path",
    "stage1_bundle_dir",
    "stage1_manifest_path",
    "stage1_voice_path",
    "effective_task_a_segments_path",
    "task_a_corrected_segments_path",
    "task_a_corrected_srt_path",
    "task_a_speaker_corrected_segments_path",
    "task_a_speaker_corrected_srt_path",
    "task_a_correction_bundle_dir",
    "task_a_correction_manifest_path",
    "task_a_correction_report_path",
    "task_a_manifest_path",
    "task_a_segments_path",
    "task_b_manifest_path",
    "task_b_matches_path",
    "task_b_profiles_path",
    "task_b_registry_path",
    "task_b_voice_bank_path",
    "task_c_manifest_path",
    "task_c_translation_path",
    "task_d_report_path",
    "task_d_stage_manifest_path",
    "task_e_dub_voice_path",
    "task_e_manifest_path",
    "task_e_mix_report_path",
    "task_e_preview_mix_path",
    "task_e_timeline_path",
]
