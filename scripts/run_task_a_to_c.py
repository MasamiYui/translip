from __future__ import annotations

import argparse
from pathlib import Path

from video_voice_separate.pipeline.runner import separate_file
from video_voice_separate.speakers.runner import build_speaker_registry
from video_voice_separate.translation.runner import translate_script
from video_voice_separate.types import SeparationRequest, SpeakerRegistryRequest, TranscriptionRequest, TranslationRequest
from video_voice_separate.transcription.runner import transcribe_file


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run stage 1 and tasks A-C in sequence.")
    parser.add_argument("--input", required=True, help="Input video or audio path")
    parser.add_argument("--output-root", default="tmp/e2e-task-a-to-c", help="Output root directory")
    parser.add_argument("--target-lang", default="en", help="Task C target language")
    parser.add_argument(
        "--translation-backend",
        default="local-m2m100",
        choices=["local-m2m100", "siliconflow"],
        help="Task C translation backend",
    )
    parser.add_argument("--glossary", default="config/glossary.example.json", help="Optional glossary path")
    parser.add_argument("--device", default="auto", choices=["auto", "cpu", "cuda", "mps"])
    parser.add_argument("--api-model", default=None, help="Optional SiliconFlow model override")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    output_root = Path(args.output_root).expanduser().resolve()

    separation = separate_file(
        SeparationRequest(
            input_path=args.input,
            mode="dialogue",
            output_dir=output_root / "stage1",
            quality="balanced",
            output_format="mp3",
            device=args.device,
        )
    )
    transcription = transcribe_file(
        TranscriptionRequest(
            input_path=separation.artifacts.voice_path,
            output_dir=output_root / "task-a",
            language="zh",
            device=args.device,
        )
    )
    registry = build_speaker_registry(
        SpeakerRegistryRequest(
            segments_path=transcription.artifacts.segments_json_path,
            audio_path=separation.artifacts.voice_path,
            output_dir=output_root / "task-b",
            registry_path=output_root / "task-b" / "registry" / "speaker_registry.json",
            update_registry=True,
            device=args.device,
        )
    )
    translation = translate_script(
        TranslationRequest(
            segments_path=transcription.artifacts.segments_json_path,
            profiles_path=registry.artifacts.profiles_path,
            output_dir=output_root / "task-c",
            target_lang=args.target_lang,
            backend=args.translation_backend,
            glossary_path=args.glossary,
            device=args.device,
            api_model=args.api_model,
        )
    )

    print(f"stage1_voice={separation.artifacts.voice_path}")
    print(f"task_a_segments={transcription.artifacts.segments_json_path}")
    print(f"task_b_profiles={registry.artifacts.profiles_path}")
    print(f"task_c_translation={translation.artifacts.translation_json_path}")
    print(f"task_c_manifest={translation.artifacts.manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
