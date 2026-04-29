from pathlib import Path
from types import SimpleNamespace

from translip.cli import build_parser, main


def test_cli_run_parser() -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "run",
            "--input",
            "sample.mp4",
            "--mode",
            "music",
            "--output-format",
            "mp3",
            "--quality",
            "high",
        ]
    )
    assert args.command == "run"
    assert args.input == "sample.mp4"
    assert args.mode == "music"
    assert args.output_format == "mp3"
    assert args.quality == "high"


def test_cli_transcribe_parser() -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "transcribe",
            "--input",
            "voice.wav",
            "--output-dir",
            "output-transcribe",
            "--language",
            "zh",
            "--asr-model",
            "small",
            "--no-srt",
        ]
    )
    assert args.command == "transcribe"
    assert args.input == "voice.wav"
    assert args.output_dir == "output-transcribe"
    assert args.language == "zh"
    assert args.asr_model == "small"
    assert args.no_srt is True


def test_parse_correct_asr_with_ocr_command() -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "correct-asr-with-ocr",
            "--segments",
            "task-a/voice/segments.zh.json",
            "--ocr-events",
            "ocr-detect/ocr_events.json",
            "--output-dir",
            "asr-ocr-correct",
            "--preset",
            "standard",
        ]
    )

    assert args.command == "correct-asr-with-ocr"
    assert args.segments == "task-a/voice/segments.zh.json"
    assert args.ocr_events == "ocr-detect/ocr_events.json"
    assert args.output_dir == "asr-ocr-correct"
    assert args.preset == "standard"


def test_cli_benchmark_transcription_parser() -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "benchmark-transcription",
            "--input",
            "sample.mp4",
            "--reference-srt",
            "sample.srt",
            "--output-dir",
            "benchmark-output",
            "--asr-model",
            "medium",
        ]
    )
    assert args.command == "benchmark-transcription"
    assert args.input == "sample.mp4"
    assert args.reference_srt == "sample.srt"
    assert args.output_dir == "benchmark-output"
    assert args.asr_model == "medium"


def test_cli_build_speaker_registry_parser() -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "build-speaker-registry",
            "--segments",
            "segments.zh.json",
            "--audio",
            "voice.wav",
            "--registry",
            "registry/speaker_registry.json",
            "--update-registry",
        ]
    )
    assert args.command == "build-speaker-registry"
    assert args.segments == "segments.zh.json"
    assert args.audio == "voice.wav"
    assert args.registry == "registry/speaker_registry.json"
    assert args.update_registry is True


def test_cli_build_voice_bank_parser() -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "build-voice-bank",
            "--profiles",
            "speaker_profiles.json",
            "--output-dir",
            "task-b/voice",
            "--task-d-report",
            "task-d/voice/spk_0000/speaker_segments.en.json",
            "--target-lang",
            "en",
            "--max-references-per-speaker",
            "5",
            "--no-composite",
        ]
    )
    assert args.command == "build-voice-bank"
    assert args.profiles == "speaker_profiles.json"
    assert args.output_dir == "task-b/voice"
    assert args.task_d_reports == ["task-d/voice/spk_0000/speaker_segments.en.json"]
    assert args.max_references_per_speaker == 5
    assert args.no_composite is True


def test_cli_main_build_speaker_registry_command(monkeypatch, capsys) -> None:
    captured: dict[str, object] = {}

    def fake_build_speaker_registry(request):
        captured["request"] = request
        return SimpleNamespace(
            artifacts=SimpleNamespace(
                profiles_path=Path("/tmp/profiles.json"),
                matches_path=Path("/tmp/matches.json"),
                registry_snapshot_path=Path("/tmp/registry.json"),
                manifest_path=Path("/tmp/manifest.json"),
            )
        )

    monkeypatch.setattr("translip.cli.configure_logging", lambda *, verbose: None)
    monkeypatch.setattr("translip.cli.build_speaker_registry", fake_build_speaker_registry)

    exit_code = main(
        [
            "build-speaker-registry",
            "--segments",
            "segments.zh.json",
            "--audio",
            "voice.wav",
            "--output-dir",
            "output-speakers",
            "--registry",
            "registry/speaker_registry.json",
            "--device",
            "auto",
            "--top-k",
            "3",
            "--update-registry",
        ]
    )

    assert exit_code == 0
    assert captured["request"].segments_path == "segments.zh.json"
    assert captured["request"].audio_path == "voice.wav"
    assert captured["request"].output_dir == "output-speakers"
    assert captured["request"].registry_path == "registry/speaker_registry.json"
    assert captured["request"].device == "auto"
    assert captured["request"].top_k == 3
    assert captured["request"].update_registry is True

    stdout = capsys.readouterr().out
    assert "profiles=/tmp/profiles.json" in stdout
    assert "matches=/tmp/matches.json" in stdout
    assert "registry=/tmp/registry.json" in stdout
    assert "manifest=/tmp/manifest.json" in stdout


def test_cli_translate_script_parser() -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "translate-script",
            "--segments",
            "segments.zh.json",
            "--profiles",
            "speaker_profiles.json",
            "--target-lang",
            "ja",
            "--backend",
            "siliconflow",
            "--api-model",
            "deepseek-ai/DeepSeek-V3",
        ]
    )
    assert args.command == "translate-script"
    assert args.segments == "segments.zh.json"
    assert args.profiles == "speaker_profiles.json"
    assert args.target_lang == "ja"
    assert args.backend == "siliconflow"
    assert args.api_model == "deepseek-ai/DeepSeek-V3"


def test_cli_synthesize_speaker_parser() -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "synthesize-speaker",
            "--translation",
            "translation.en.json",
            "--profiles",
            "speaker_profiles.json",
            "--speaker-id",
            "spk_0000",
            "--backend",
            "qwen3tts",
            "--voice-bank",
            "voice_bank.en.json",
            "--segment-id",
            "seg-0001",
            "--segment-id",
            "seg-0002",
            "--max-segments",
            "2",
        ]
    )
    assert args.command == "synthesize-speaker"
    assert args.translation == "translation.en.json"
    assert args.profiles == "speaker_profiles.json"
    assert args.speaker_id == "spk_0000"
    assert args.backend == "qwen3tts"
    assert args.voice_bank == "voice_bank.en.json"
    assert args.segment_ids == ["seg-0001", "seg-0002"]
    assert args.max_segments == 2


def test_cli_synthesize_speaker_defaults_to_moss_tts_nano_onnx() -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "synthesize-speaker",
            "--translation",
            "translation.en.json",
            "--profiles",
            "speaker_profiles.json",
            "--speaker-id",
            "spk_0000",
        ]
    )
    assert args.backend == "moss-tts-nano-onnx"


def test_cli_synthesize_speaker_accepts_moss_tts_nano_onnx() -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "synthesize-speaker",
            "--translation",
            "translation.en.json",
            "--profiles",
            "speaker_profiles.json",
            "--speaker-id",
            "spk_0000",
            "--backend",
            "moss-tts-nano-onnx",
        ]
    )
    assert args.backend == "moss-tts-nano-onnx"


def test_cli_render_dub_parser() -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "render-dub",
            "--background",
            "background.mp3",
            "--segments",
            "segments.zh.json",
            "--translation",
            "translation.en.json",
            "--task-d-report",
            "spk_0000/speaker_segments.en.json",
            "--task-d-report",
            "spk_0001/speaker_segments.en.json",
            "--selected-segments",
            "repair/selected_segments.en.json",
            "--quality-gate",
            "strict",
            "--fit-policy",
            "high_quality",
            "--fit-backend",
            "atempo",
            "--mix-profile",
            "enhanced",
            "--ducking-mode",
            "sidechain",
            "--preview-format",
            "mp3",
        ]
    )
    assert args.command == "render-dub"
    assert args.background == "background.mp3"
    assert args.segments == "segments.zh.json"
    assert args.translation == "translation.en.json"
    assert args.task_d_reports == [
        "spk_0000/speaker_segments.en.json",
        "spk_0001/speaker_segments.en.json",
    ]
    assert args.selected_segments == "repair/selected_segments.en.json"
    assert args.quality_gate == "strict"
    assert args.fit_policy == "high_quality"
    assert args.fit_backend == "atempo"
    assert args.mix_profile == "enhanced"
    assert args.ducking_mode == "sidechain"
    assert args.preview_format == "mp3"


def test_cli_run_dub_repair_parser() -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "run-dub-repair",
            "--repair-queue",
            "repair_queue.en.json",
            "--rewrite-plan",
            "rewrite_plan.en.json",
            "--reference-plan",
            "reference_plan.en.json",
            "--tts-backend",
            "moss-tts-nano-onnx",
            "--tts-backend",
            "qwen3tts",
            "--segment-id",
            "seg-0001",
            "--max-items",
            "5",
            "--attempts-per-item",
            "4",
            "--include-risk",
        ]
    )
    assert args.command == "run-dub-repair"
    assert args.repair_queue == "repair_queue.en.json"
    assert args.rewrite_plan == "rewrite_plan.en.json"
    assert args.reference_plan == "reference_plan.en.json"
    assert args.tts_backends == ["moss-tts-nano-onnx", "qwen3tts"]
    assert args.segment_ids == ["seg-0001"]
    assert args.max_items == 5
    assert args.attempts_per_item == 4
    assert args.include_risk is True


def test_cli_run_pipeline_parser() -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "run-pipeline",
            "--input",
            "sample.mp4",
            "--output-root",
            "pipeline-output",
            "--target-lang",
            "en",
            "--resume",
            "--write-status",
        ]
    )
    assert args.command == "run-pipeline"
    assert args.input == "sample.mp4"
    assert args.output_root == "pipeline-output"
    assert args.target_lang == "en"
    assert args.resume is True
    assert args.write_status is True


def test_cli_run_pipeline_parser_leaves_optional_overrides_unset() -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "run-pipeline",
            "--input",
            "sample.mp4",
        ]
    )
    assert args.output_root is None
    assert args.run_from_stage is None
    assert args.run_to_stage is None
    assert args.write_status is None
    assert args.status_update_interval_sec is None


def test_cli_run_pipeline_parser_accepts_template_and_policy() -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "run-pipeline",
            "--input",
            "sample.mp4",
            "--template",
            "asr-dub+ocr-subs",
            "--subtitle-source",
            "both",
            "--video-source",
            "clean_if_available",
        ]
    )

    assert args.template == "asr-dub+ocr-subs"
    assert args.subtitle_source == "both"
    assert args.video_source == "clean_if_available"


def test_cli_run_pipeline_parser_accepts_external_project_roots() -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "run-pipeline",
            "--input",
            "sample.mp4",
            "--ocr-project-root",
            "/tmp/subtitle-ocr",
            "--erase-project-root",
            "/tmp/video-subtitle-erasure",
        ]
    )

    assert args.ocr_project_root == "/tmp/subtitle-ocr"
    assert args.erase_project_root == "/tmp/video-subtitle-erasure"


def test_cli_export_video_parser() -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "export-video",
            "--pipeline-root",
            "output-pipeline",
            "--output-dir",
            "delivery",
            "--target-lang",
            "en",
            "--no-export-dub",
            "--video-codec",
            "copy",
            "--audio-codec",
            "aac",
        ]
    )
    assert args.command == "export-video"
    assert args.pipeline_root == "output-pipeline"
    assert args.output_dir == "delivery"
    assert args.target_lang == "en"
    assert args.export_preview is True
    assert args.export_dub is False
    assert args.video_codec == "copy"
    assert args.audio_codec == "aac"
