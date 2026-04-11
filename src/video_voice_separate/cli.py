from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import DEFAULT_DEVICE, DEFAULT_MODE, DEFAULT_OUTPUT_FORMAT
from .models.cdx23_dialogue import Cdx23DialogueSeparator
from .pipeline.ingest import probe_input
from .pipeline.runner import separate_file
from .types import SeparationRequest
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

    parser.error("Unknown command")
    return 2
