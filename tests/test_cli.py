from video_voice_separate.cli import build_parser


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
