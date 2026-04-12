from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import (
    DEFAULT_DEVICE,
    DEFAULT_DUBBING_BACKEND,
    DEFAULT_DUBBING_BACKREAD_MODEL,
    DEFAULT_MODE,
    DEFAULT_OUTPUT_FORMAT,
    DEFAULT_TRANSLATION_BACKEND,
    DEFAULT_TRANSLATION_BATCH_SIZE,
    DEFAULT_TRANSLATION_LOCAL_MODEL,
    DEFAULT_TRANSLATION_SOURCE_LANG,
    DEFAULT_TRANSLATION_TARGET_LANG,
    DEFAULT_TRANSCRIPTION_ASR_MODEL,
    DEFAULT_TRANSCRIPTION_LANGUAGE,
)
from .dubbing.runner import synthesize_speaker
from .models.cdx23_dialogue import Cdx23DialogueSeparator
from .pipeline.ingest import probe_input
from .pipeline.runner import separate_file
from .speakers.runner import build_speaker_registry
from .translation.runner import translate_script
from .transcription.runner import transcribe_file
from .types import (
    DubbingRequest,
    SeparationRequest,
    SpeakerRegistryRequest,
    TranscriptionRequest,
    TranslationRequest,
)
from .utils.logging import configure_logging


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="video-voice-separate")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Separate a media file")
    run_parser.add_argument("--input", required=True, help="Input media file path")
    run_parser.add_argument("--mode", default=DEFAULT_MODE, choices=["music", "dialogue", "auto"])
    run_parser.add_argument("--output-dir", default="output", help="Output directory")
    run_parser.add_argument(
        "--output-format",
        default=DEFAULT_OUTPUT_FORMAT,
        choices=["wav", "mp3", "flac", "aac", "opus"],
    )
    run_parser.add_argument(
        "--quality",
        default="balanced",
        choices=["balanced", "high"],
        help="balanced uses htdemucs for speed, high uses htdemucs_ft for quality",
    )
    run_parser.add_argument(
        "--music-model",
        default=None,
        help="Override the Demucs model name directly, e.g. htdemucs or htdemucs_ft",
    )
    run_parser.add_argument("--sample-rate", type=int, default=None)
    run_parser.add_argument("--bitrate", default=None)
    run_parser.add_argument("--enhance-voice", action="store_true")
    run_parser.add_argument("--device", default=DEFAULT_DEVICE, choices=["auto", "cpu", "cuda", "mps"])
    run_parser.add_argument("--keep-intermediate", action="store_true")
    run_parser.add_argument("--backend-music", default="demucs")
    run_parser.add_argument("--backend-dialogue", default="cdx23")
    run_parser.add_argument("--audio-stream-index", type=int, default=0)

    transcribe_parser = subparsers.add_parser(
        "transcribe",
        help="Generate speaker-attributed transcript from a voice track or media file",
    )
    transcribe_parser.add_argument("--input", required=True, help="Input media file path")
    transcribe_parser.add_argument("--output-dir", default="output-transcribe", help="Output directory")
    transcribe_parser.add_argument(
        "--language",
        default=DEFAULT_TRANSCRIPTION_LANGUAGE,
        help="Language hint for ASR, e.g. zh",
    )
    transcribe_parser.add_argument(
        "--asr-model",
        default=DEFAULT_TRANSCRIPTION_ASR_MODEL,
        help="faster-whisper model name, e.g. small, medium, large-v3",
    )
    transcribe_parser.add_argument("--device", default=DEFAULT_DEVICE, choices=["auto", "cpu", "cuda", "mps"])
    transcribe_parser.add_argument("--audio-stream-index", type=int, default=0)
    transcribe_parser.add_argument("--keep-intermediate", action="store_true")
    transcribe_parser.add_argument("--no-srt", action="store_true")

    speaker_parser = subparsers.add_parser(
        "build-speaker-registry",
        help="Build speaker profiles and match them against a file-backed speaker registry",
    )
    speaker_parser.add_argument("--segments", required=True, help="Task A segments.zh.json path")
    speaker_parser.add_argument("--audio", required=True, help="Voice track path")
    speaker_parser.add_argument("--output-dir", default="output-speakers", help="Output directory")
    speaker_parser.add_argument("--registry", default=None, help="Registry JSON path")
    speaker_parser.add_argument("--device", default=DEFAULT_DEVICE, choices=["auto", "cpu", "cuda", "mps"])
    speaker_parser.add_argument("--top-k", type=int, default=3)
    speaker_parser.add_argument("--update-registry", action="store_true")
    speaker_parser.add_argument("--keep-intermediate", action="store_true")

    translate_parser = subparsers.add_parser(
        "translate-script",
        help="Generate a multilingual translation script for downstream dubbing",
    )
    translate_parser.add_argument("--segments", required=True, help="Task A segments.zh.json path")
    translate_parser.add_argument("--profiles", required=True, help="Task B speaker_profiles.json path")
    translate_parser.add_argument("--output-dir", default="output-task-c", help="Output directory")
    translate_parser.add_argument(
        "--source-lang",
        default=DEFAULT_TRANSLATION_SOURCE_LANG,
        help="Source language code, e.g. zh or auto",
    )
    translate_parser.add_argument(
        "--target-lang",
        default=DEFAULT_TRANSLATION_TARGET_LANG,
        help="Target language code, e.g. en or ja",
    )
    translate_parser.add_argument(
        "--backend",
        default=DEFAULT_TRANSLATION_BACKEND,
        choices=["local-m2m100", "siliconflow"],
    )
    translate_parser.add_argument("--device", default=DEFAULT_DEVICE, choices=["auto", "cpu", "cuda", "mps"])
    translate_parser.add_argument("--glossary", default=None, help="Optional glossary JSON path")
    translate_parser.add_argument("--batch-size", type=int, default=DEFAULT_TRANSLATION_BATCH_SIZE)
    translate_parser.add_argument(
        "--local-model",
        default=DEFAULT_TRANSLATION_LOCAL_MODEL,
        help="Local translation model name for the M2M100 backend",
    )
    translate_parser.add_argument("--api-model", default=None, help="Override SiliconFlow model name")
    translate_parser.add_argument("--api-base-url", default=None, help="Override SiliconFlow base URL")

    synthesize_parser = subparsers.add_parser(
        "synthesize-speaker",
        help="Synthesize target-language audio for a single speaker from Task B/C artifacts",
    )
    synthesize_parser.add_argument("--translation", required=True, help="Task C translation.<target_tag>.json path")
    synthesize_parser.add_argument("--profiles", required=True, help="Task B speaker_profiles.json path")
    synthesize_parser.add_argument("--speaker-id", required=True, help="Speaker id to synthesize, e.g. spk_0000")
    synthesize_parser.add_argument("--output-dir", default="output-task-d", help="Output directory")
    synthesize_parser.add_argument(
        "--backend",
        default=DEFAULT_DUBBING_BACKEND,
        choices=["f5tts", "openvoice"],
    )
    synthesize_parser.add_argument("--device", default=DEFAULT_DEVICE, choices=["auto", "cpu", "cuda", "mps"])
    synthesize_parser.add_argument("--reference-clip", default=None, help="Optional reference clip override")
    synthesize_parser.add_argument(
        "--segment-id",
        action="append",
        dest="segment_ids",
        help="Limit synthesis to selected segment ids; may be passed multiple times",
    )
    synthesize_parser.add_argument(
        "--max-segments",
        type=int,
        default=None,
        help="Optional cap on the number of synthesized segments after filtering",
    )
    synthesize_parser.add_argument(
        "--backread-model",
        default=DEFAULT_DUBBING_BACKREAD_MODEL,
        help="faster-whisper model name used for generated-audio backread checks",
    )
    synthesize_parser.add_argument("--keep-intermediate", action="store_true")

    probe_parser = subparsers.add_parser("probe", help="Inspect a media file")
    probe_parser.add_argument("--input", required=True, help="Input media file path")

    download_parser = subparsers.add_parser(
        "download-models",
        help="Download external model weights into the local cache",
    )
    download_parser.add_argument(
        "--backend",
        default="cdx23",
        choices=["cdx23"],
        help="Model backend to download",
    )
    download_parser.add_argument(
        "--quality",
        default="balanced",
        choices=["balanced", "high"],
        help="Checkpoint set to download",
    )
    download_parser.add_argument("--force", action="store_true", help="Redownload weights")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    configure_logging(verbose=args.verbose)

    if args.command == "probe":
        media_info = probe_input(Path(args.input).expanduser().resolve())
        print(
            json.dumps(
                {
                    "path": str(media_info.path),
                    "media_type": media_info.media_type,
                    "format_name": media_info.format_name,
                    "duration_sec": media_info.duration_sec,
                    "audio_stream_index": media_info.audio_stream_index,
                    "audio_stream_count": media_info.audio_stream_count,
                    "sample_rate": media_info.sample_rate,
                    "channels": media_info.channels,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.command == "download-models":
        if args.backend == "cdx23":
            separator = Cdx23DialogueSeparator(quality=args.quality, device="cpu")
            downloaded = separator.ensure_weights(force=args.force)
            for path in downloaded:
                print(path)
            return 0
        parser.error(f"Unsupported backend: {args.backend}")
        return 2

    if args.command == "run":
        request = SeparationRequest(
            input_path=args.input,
            mode=args.mode,
            output_dir=args.output_dir,
            output_format=args.output_format,
            quality=args.quality,
            music_model=args.music_model,
            sample_rate=args.sample_rate,
            bitrate=args.bitrate,
            enhance_voice=args.enhance_voice,
            device=args.device,
            keep_intermediate=args.keep_intermediate,
            backend_music=args.backend_music,
            backend_dialogue=args.backend_dialogue,
            audio_stream_index=args.audio_stream_index,
        )
        result = separate_file(request)
        print(f"voice={result.artifacts.voice_path}")
        print(f"background={result.artifacts.background_path}")
        print(f"manifest={result.artifacts.manifest_path}")
        return 0

    if args.command == "transcribe":
        request = TranscriptionRequest(
            input_path=args.input,
            output_dir=args.output_dir,
            language=args.language,
            asr_model=args.asr_model,
            device=args.device,
            audio_stream_index=args.audio_stream_index,
            keep_intermediate=args.keep_intermediate,
            write_srt=not args.no_srt,
        )
        result = transcribe_file(request)
        print(f"segments={result.artifacts.segments_json_path}")
        if result.artifacts.srt_path:
            print(f"srt={result.artifacts.srt_path}")
        print(f"manifest={result.artifacts.manifest_path}")
        return 0

    if args.command == "build-speaker-registry":
        request = SpeakerRegistryRequest(
            segments_path=args.segments,
            audio_path=args.audio,
            output_dir=args.output_dir,
            registry_path=args.registry,
            device=args.device,
            top_k=args.top_k,
            update_registry=args.update_registry,
            keep_intermediate=args.keep_intermediate,
        )
        result = build_speaker_registry(request)
        print(f"profiles={result.artifacts.profiles_path}")
        print(f"matches={result.artifacts.matches_path}")
        print(f"registry={result.artifacts.registry_snapshot_path}")
        print(f"manifest={result.artifacts.manifest_path}")
        return 0

    if args.command == "translate-script":
        request = TranslationRequest(
            segments_path=args.segments,
            profiles_path=args.profiles,
            output_dir=args.output_dir,
            source_lang=args.source_lang,
            target_lang=args.target_lang,
            backend=args.backend,
            device=args.device,
            glossary_path=args.glossary,
            batch_size=args.batch_size,
            local_model=args.local_model,
            api_model=args.api_model,
            api_base_url=args.api_base_url,
        )
        result = translate_script(request)
        print(f"translation={result.artifacts.translation_json_path}")
        print(f"editable={result.artifacts.editable_json_path}")
        print(f"srt={result.artifacts.srt_path}")
        print(f"manifest={result.artifacts.manifest_path}")
        return 0

    if args.command == "synthesize-speaker":
        request = DubbingRequest(
            translation_path=args.translation,
            profiles_path=args.profiles,
            output_dir=args.output_dir,
            speaker_id=args.speaker_id,
            backend=args.backend,
            device=args.device,
            reference_clip_path=args.reference_clip,
            segment_ids=args.segment_ids,
            max_segments=args.max_segments,
            keep_intermediate=args.keep_intermediate,
            backread_model=args.backread_model,
        )
        result = synthesize_speaker(request)
        if result.artifacts.demo_audio_path:
            print(f"demo={result.artifacts.demo_audio_path}")
        print(f"segments={result.artifacts.segments_dir}")
        print(f"report={result.artifacts.report_path}")
        print(f"manifest={result.artifacts.manifest_path}")
        return 0

    parser.error("Unknown command")
    return 2
