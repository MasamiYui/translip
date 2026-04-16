from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import (
    DEFAULT_CONDENSE_MODE,
    DEFAULT_DEVICE,
    DEFAULT_DELIVERY_AUDIO_BITRATE,
    DEFAULT_DELIVERY_AUDIO_CODEC,
    DEFAULT_DELIVERY_CONTAINER,
    DEFAULT_DELIVERY_END_POLICY,
    DEFAULT_DELIVERY_VIDEO_CODEC,
    DEFAULT_DUBBING_BACKEND,
    DEFAULT_DUBBING_BACKREAD_MODEL,
    DEFAULT_MODE,
    DEFAULT_OUTPUT_FORMAT,
    DEFAULT_RENDER_BACKGROUND_GAIN_DB,
    DEFAULT_RENDER_DUCKING_MODE,
    DEFAULT_RENDER_FIT_BACKEND,
    DEFAULT_RENDER_FIT_POLICY,
    DEFAULT_RENDER_MIX_PROFILE,
    DEFAULT_RENDER_OUTPUT_SAMPLE_RATE,
    DEFAULT_RENDER_PREVIEW_FORMAT,
    DEFAULT_RENDER_WINDOW_DUCKING_DB,
    DEFAULT_TRANSLATION_BACKEND,
    DEFAULT_TRANSLATION_BATCH_SIZE,
    DEFAULT_TRANSLATION_LOCAL_MODEL,
    DEFAULT_TRANSLATION_SOURCE_LANG,
    DEFAULT_TRANSLATION_TARGET_LANG,
    DEFAULT_TRANSCRIPTION_ASR_MODEL,
    DEFAULT_TRANSCRIPTION_LANGUAGE,
)
from .delivery.runner import export_video
from .dubbing.runner import synthesize_speaker
from .models.cdx23_dialogue import Cdx23DialogueSeparator
from .orchestration.request import build_pipeline_request
from .orchestration.runner import run_pipeline
from .pipeline.ingest import probe_input
from .pipeline.runner import separate_file
from .rendering.runner import render_dub
from .speakers.runner import build_speaker_registry
from .subtitles.preview import SubtitlePreviewRequest, preview_subtitle
from .translation.runner import translate_script
from .transcription.runner import transcribe_file
from .types import (
    DubbingRequest,
    ExportVideoRequest,
    RenderDubRequest,
    SeparationRequest,
    SpeakerRegistryRequest,
    SubtitleStyle,
    TranscriptionRequest,
    TranslationRequest,
)
from .utils.logging import configure_logging


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="translip")
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
    translate_parser.add_argument(
        "--condense-mode",
        default=DEFAULT_CONDENSE_MODE,
        choices=["off", "smart", "aggressive"],
        help="LLM-based translation condensation for overflowing TTS segments",
    )

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
        choices=["qwen3tts"],
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

    render_parser = subparsers.add_parser(
        "render-dub",
        help="Assemble Task D speaker outputs into a target-language dub timeline and preview mix",
    )
    render_parser.add_argument("--background", required=True, help="Background audio path from stage 1")
    render_parser.add_argument("--segments", required=True, help="Task A segments.zh.json path")
    render_parser.add_argument("--translation", required=True, help="Task C translation.<lang>.json path")
    render_parser.add_argument(
        "--task-d-report",
        action="append",
        dest="task_d_reports",
        required=True,
        help="Task D speaker_segments.<lang>.json path; may be passed multiple times",
    )
    render_parser.add_argument("--output-dir", default="output-task-e", help="Output directory")
    render_parser.add_argument(
        "--target-lang",
        default=DEFAULT_TRANSLATION_TARGET_LANG,
        help="Target language code, e.g. en",
    )
    render_parser.add_argument(
        "--fit-policy",
        default=DEFAULT_RENDER_FIT_POLICY,
        choices=["conservative", "high_quality"],
    )
    render_parser.add_argument(
        "--fit-backend",
        default=DEFAULT_RENDER_FIT_BACKEND,
        choices=["atempo", "rubberband"],
    )
    render_parser.add_argument(
        "--mix-profile",
        default=DEFAULT_RENDER_MIX_PROFILE,
        choices=["preview", "enhanced"],
    )
    render_parser.add_argument(
        "--ducking-mode",
        default=DEFAULT_RENDER_DUCKING_MODE,
        choices=["static", "sidechain"],
    )
    render_parser.add_argument(
        "--output-sample-rate",
        type=int,
        default=DEFAULT_RENDER_OUTPUT_SAMPLE_RATE,
    )
    render_parser.add_argument(
        "--background-gain-db",
        type=float,
        default=DEFAULT_RENDER_BACKGROUND_GAIN_DB,
    )
    render_parser.add_argument(
        "--window-ducking-db",
        type=float,
        default=DEFAULT_RENDER_WINDOW_DUCKING_DB,
    )
    render_parser.add_argument("--max-compress-ratio", type=float, default=1.45)
    render_parser.add_argument(
        "--preview-format",
        default=DEFAULT_RENDER_PREVIEW_FORMAT,
        choices=["wav", "mp3"],
    )

    probe_parser = subparsers.add_parser("probe", help="Inspect a media file")
    probe_parser.add_argument("--input", required=True, help="Input media file path")

    preview_parser = subparsers.add_parser(
        "preview-subtitles",
        help="Render a short preview video with burned subtitles",
    )
    preview_parser.add_argument("--input-video", required=True)
    preview_parser.add_argument("--subtitle", required=True)
    preview_parser.add_argument("--output", default=None)
    preview_parser.add_argument("--font-family", default="Noto Sans")
    preview_parser.add_argument("--font-size", type=int, default=0)
    preview_parser.add_argument("--position", choices=["top", "bottom"], default="bottom")
    preview_parser.add_argument("--margin-v", type=int, default=0)
    preview_parser.add_argument("--start-sec", type=float, default=None)
    preview_parser.add_argument("--duration", type=float, default=10.0)

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

    pipeline_parser = subparsers.add_parser(
        "run-pipeline",
        help="Run stage 1 through task-e with cache-aware orchestration",
    )
    pipeline_parser.add_argument("--config", default=None, help="Optional pipeline JSON config path")
    pipeline_parser.add_argument("--input", required=True, help="Input video or audio path")
    pipeline_parser.add_argument("--output-root", default=None)
    pipeline_parser.add_argument(
        "--template",
        default=None,
        choices=["asr-dub-basic", "asr-dub+ocr-subs", "asr-dub+ocr-subs+erase"],
    )
    pipeline_parser.add_argument("--ocr-project-root", default=None)
    pipeline_parser.add_argument("--erase-project-root", default=None)
    pipeline_parser.add_argument("--target-lang", default=None)
    pipeline_parser.add_argument(
        "--translation-backend",
        default=None,
        choices=["local-m2m100", "siliconflow"],
    )
    pipeline_parser.add_argument(
        "--tts-backend",
        default=None,
        choices=["qwen3tts"],
    )
    pipeline_parser.add_argument("--device", default=None, choices=["auto", "cpu", "cuda", "mps"])
    pipeline_parser.add_argument("--run-from-stage", default=None)
    pipeline_parser.add_argument("--run-to-stage", default=None)
    pipeline_parser.add_argument("--resume", action="store_true", default=None)
    pipeline_parser.add_argument("--force-stage", action="append", dest="force_stages")
    pipeline_parser.add_argument("--reuse-existing", dest="reuse_existing", action=argparse.BooleanOptionalAction, default=None)
    pipeline_parser.add_argument("--write-status", dest="write_status", action=argparse.BooleanOptionalAction, default=None)
    pipeline_parser.add_argument(
        "--status-update-interval-sec",
        type=float,
        default=None,
    )
    pipeline_parser.add_argument("--glossary-path", default=None)
    pipeline_parser.add_argument("--registry-path", default=None)
    pipeline_parser.add_argument("--api-model", default=None)
    pipeline_parser.add_argument("--api-base-url", default=None)
    pipeline_parser.add_argument(
        "--condense-mode",
        default=None,
        choices=["off", "smart", "aggressive"],
    )
    pipeline_parser.add_argument("--fit-policy", default=None, choices=["conservative", "high_quality"])
    pipeline_parser.add_argument("--fit-backend", default=None, choices=["atempo", "rubberband"])
    pipeline_parser.add_argument("--mix-profile", default=None, choices=["preview", "enhanced"])
    pipeline_parser.add_argument("--ducking-mode", default=None, choices=["static", "sidechain"])
    pipeline_parser.add_argument("--preview-format", default=None, choices=["wav", "mp3"])
    pipeline_parser.add_argument("--output-sample-rate", type=int, default=None)
    pipeline_parser.add_argument("--background-gain-db", type=float, default=None)
    pipeline_parser.add_argument("--window-ducking-db", type=float, default=None)
    pipeline_parser.add_argument("--max-compress-ratio", type=float, default=None)
    pipeline_parser.add_argument("--speaker-limit", type=int, default=None)
    pipeline_parser.add_argument("--segments-per-speaker", type=int, default=None)
    pipeline_parser.add_argument(
        "--video-source",
        default=None,
        choices=["original", "clean", "clean_if_available"],
    )
    pipeline_parser.add_argument(
        "--audio-source",
        default=None,
        choices=["preview_mix", "dub_voice", "both", "original"],
    )
    pipeline_parser.add_argument(
        "--subtitle-source",
        default=None,
        choices=["none", "asr", "ocr", "both"],
    )
    pipeline_parser.add_argument("--separation-mode", default=None, choices=["music", "dialogue", "auto"])
    pipeline_parser.add_argument("--separation-quality", default=None, choices=["balanced", "high"])
    pipeline_parser.add_argument("--stage1-output-format", default=None, choices=["wav", "mp3", "flac", "aac", "opus"])
    pipeline_parser.add_argument("--transcription-language", default=None)
    pipeline_parser.add_argument("--asr-model", default=None)
    pipeline_parser.add_argument("--audio-stream-index", type=int, default=None)
    pipeline_parser.add_argument("--top-k", type=int, default=None)
    pipeline_parser.add_argument("--update-registry", dest="update_registry", action=argparse.BooleanOptionalAction, default=None)
    pipeline_parser.add_argument("--keep-logs", dest="keep_logs", action=argparse.BooleanOptionalAction, default=None)
    pipeline_parser.add_argument("--subtitle-mode", default=None, choices=["none", "chinese_only", "english_only", "bilingual"])
    pipeline_parser.add_argument("--bilingual-chinese-position", default=None, choices=["top", "bottom"])
    pipeline_parser.add_argument("--bilingual-english-position", default=None, choices=["top", "bottom"])

    export_parser = subparsers.add_parser(
        "export-video",
        help="Mux Task E audio back into the source video and export delivery mp4 files",
    )
    export_parser.add_argument("--input-video", default=None)
    export_parser.add_argument("--pipeline-root", default=None)
    export_parser.add_argument("--task-e-dir", default=None)
    export_parser.add_argument("--output-dir", default=None)
    export_parser.add_argument("--target-lang", default=None)
    export_parser.add_argument("--export-preview", dest="export_preview", action=argparse.BooleanOptionalAction, default=True)
    export_parser.add_argument("--export-dub", dest="export_dub", action=argparse.BooleanOptionalAction, default=True)
    export_parser.add_argument("--container", choices=["mp4"], default=DEFAULT_DELIVERY_CONTAINER)
    export_parser.add_argument("--video-codec", choices=["copy", "libx264"], default=DEFAULT_DELIVERY_VIDEO_CODEC)
    export_parser.add_argument("--audio-codec", choices=["aac"], default=DEFAULT_DELIVERY_AUDIO_CODEC)
    export_parser.add_argument("--audio-bitrate", default=DEFAULT_DELIVERY_AUDIO_BITRATE)
    export_parser.add_argument(
        "--end-policy",
        choices=["trim_audio_to_video", "keep_longest"],
        default=DEFAULT_DELIVERY_END_POLICY,
    )
    export_parser.add_argument("--overwrite", dest="overwrite", action=argparse.BooleanOptionalAction, default=True)
    export_parser.add_argument("--keep-temp", dest="keep_temp", action=argparse.BooleanOptionalAction, default=False)
    export_parser.add_argument("--subtitle-mode", choices=["none", "chinese_only", "english_only", "bilingual"], default="none")
    export_parser.add_argument("--subtitle-source", choices=["ocr", "asr"], default="ocr")
    export_parser.add_argument("--subtitle-font", default="Noto Sans")
    export_parser.add_argument("--subtitle-font-size", type=int, default=0)
    export_parser.add_argument("--subtitle-color", default="#FFFFFF")
    export_parser.add_argument("--subtitle-outline-color", default="#000000")
    export_parser.add_argument("--subtitle-outline-width", type=float, default=2.0)
    export_parser.add_argument("--subtitle-position", choices=["top", "bottom"], default="bottom")
    export_parser.add_argument("--subtitle-margin-v", type=int, default=0)
    export_parser.add_argument("--subtitle-bold", action="store_true")
    export_parser.add_argument("--bilingual-chinese-position", choices=["top", "bottom"], default="bottom")
    export_parser.add_argument("--bilingual-english-position", choices=["top", "bottom"], default="top")
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

    if args.command == "preview-subtitles":
        style = SubtitleStyle(
            font_family=args.font_family,
            font_size=args.font_size,
            primary_color="#FFFFFF",
            outline_color="#000000",
            outline_width=2.0,
            shadow_depth=1.0,
            bold=False,
            position=args.position,
            margin_v=args.margin_v,
            margin_h=20,
            alignment=8 if args.position == "top" else 2,
        )
        result = preview_subtitle(
            SubtitlePreviewRequest(
                input_video_path=args.input_video,
                subtitle_path=args.subtitle,
                output_path=args.output,
                style=style,
                start_sec=args.start_sec,
                duration_sec=args.duration,
            )
        )
        print(f"preview_video={result.preview_path}")
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
            condense_mode=args.condense_mode,
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

    if args.command == "render-dub":
        request = RenderDubRequest(
            background_path=args.background,
            segments_path=args.segments,
            translation_path=args.translation,
            task_d_report_paths=args.task_d_reports,
            output_dir=args.output_dir,
            target_lang=args.target_lang,
            fit_policy=args.fit_policy,
            fit_backend=args.fit_backend,
            mix_profile=args.mix_profile,
            ducking_mode=args.ducking_mode,
            output_sample_rate=args.output_sample_rate,
            background_gain_db=args.background_gain_db,
            window_ducking_db=args.window_ducking_db,
            max_compress_ratio=args.max_compress_ratio,
            preview_format=args.preview_format,
        )
        result = render_dub(request)
        print(f"dub_voice={result.artifacts.dub_voice_path}")
        print(f"preview_mix_wav={result.artifacts.preview_mix_wav_path}")
        if result.artifacts.preview_mix_extra_path:
            print(f"preview_mix_extra={result.artifacts.preview_mix_extra_path}")
        print(f"timeline={result.artifacts.timeline_path}")
        print(f"mix_report={result.artifacts.mix_report_path}")
        print(f"manifest={result.artifacts.manifest_path}")
        return 0

    if args.command == "run-pipeline":
        request = build_pipeline_request(vars(args))
        result = run_pipeline(request)
        print(f"pipeline_manifest={result.manifest_path}")
        print(f"pipeline_report={result.report_path}")
        print(f"pipeline_status={result.status_path}")
        print(f"task_e_dub_voice={result.report['final_artifacts'].get('dub_voice_path')}")
        print(f"task_e_preview_mix={result.report['final_artifacts'].get('preview_mix_path')}")
        return 0

    if args.command == "export-video":
        request = ExportVideoRequest(
            input_video_path=args.input_video,
            pipeline_root=args.pipeline_root,
            task_e_dir=args.task_e_dir,
            output_dir=args.output_dir,
            target_lang=args.target_lang,
            export_preview=args.export_preview,
            export_dub=args.export_dub,
            container=args.container,
            video_codec=args.video_codec,
            audio_codec=args.audio_codec,
            audio_bitrate=args.audio_bitrate,
            end_policy=args.end_policy,
            overwrite=args.overwrite,
            keep_temp=args.keep_temp,
            subtitle_mode=args.subtitle_mode,
            subtitle_source=args.subtitle_source,
            subtitle_style=SubtitleStyle(
                font_family=args.subtitle_font,
                font_size=args.subtitle_font_size,
                primary_color=args.subtitle_color,
                outline_color=args.subtitle_outline_color,
                outline_width=args.subtitle_outline_width,
                shadow_depth=1.0,
                bold=args.subtitle_bold,
                position=args.subtitle_position,
                margin_v=args.subtitle_margin_v,
                margin_h=20,
                alignment=8 if args.subtitle_position == "top" else 2,
            ),
            bilingual_chinese_position=args.bilingual_chinese_position,
            bilingual_english_position=args.bilingual_english_position,
        )
        result = export_video(request)
        if result.artifacts.preview_video_path:
            print(f"final_preview_video={result.artifacts.preview_video_path}")
        if result.artifacts.dub_video_path:
            print(f"final_dub_video={result.artifacts.dub_video_path}")
        print(f"delivery_manifest={result.artifacts.manifest_path}")
        print(f"delivery_report={result.artifacts.report_path}")
        return 0

    parser.error("Unknown command")
    return 2
