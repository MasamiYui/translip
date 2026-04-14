from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from video_voice_separate.dubbing.planning import (
    pick_segment_ids_for_speaker,
    pick_task_d_speaker_ids,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run stage 1 and tasks A-D in sequence.")
    parser.add_argument("--input", required=True, help="Input video or audio path")
    parser.add_argument("--output-root", default="tmp/e2e-task-a-to-d", help="Output root directory")
    parser.add_argument("--target-lang", default="en", help="Task C/D target language")
    parser.add_argument(
        "--translation-backend",
        default="local-m2m100",
        choices=["local-m2m100", "siliconflow"],
        help="Task C translation backend",
    )
    parser.add_argument("--tts-backend", default="qwen3tts", choices=["qwen3tts"])
    parser.add_argument("--speaker-id", default=None, help="Optional speaker id override for Task D")
    parser.add_argument("--glossary", default="config/glossary.example.json", help="Optional glossary path")
    parser.add_argument("--device", default="auto", choices=["auto", "cpu", "cuda", "mps"])
    parser.add_argument("--api-model", default=None, help="Optional SiliconFlow model override")
    parser.add_argument("--max-segments", type=int, default=None, help="Optional Task D segment cap")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    input_path = Path(args.input).expanduser().resolve()
    output_root = Path(args.output_root).expanduser().resolve()

    stage1_dir = output_root / "stage1"
    task_a_dir = output_root / "task-a"
    task_b_dir = output_root / "task-b"
    task_c_dir = output_root / "task-c"
    task_d_dir = output_root / "task-d"
    source_bundle = stage1_dir / input_path.stem

    _run_cli(
        [
            "run",
            "--input",
            str(input_path),
            "--mode",
            "dialogue",
            "--output-dir",
            str(stage1_dir),
            "--quality",
            "balanced",
            "--output-format",
            "mp3",
            "--device",
            args.device,
        ]
    )
    voice_path = source_bundle / "voice.mp3"

    _run_cli(
        [
            "transcribe",
            "--input",
            str(voice_path),
            "--output-dir",
            str(task_a_dir),
            "--language",
            "zh",
            "--device",
            args.device,
        ]
    )
    task_a_segments = task_a_dir / "voice" / "segments.zh.json"

    _run_cli(
        [
            "build-speaker-registry",
            "--segments",
            str(task_a_segments),
            "--audio",
            str(voice_path),
            "--output-dir",
            str(task_b_dir),
            "--registry",
            str(task_b_dir / "registry" / "speaker_registry.json"),
            "--update-registry",
            "--device",
            args.device,
        ]
    )
    task_b_profiles = task_b_dir / "voice" / "speaker_profiles.json"

    translate_cmd = [
        "translate-script",
        "--segments",
        str(task_a_segments),
        "--profiles",
        str(task_b_profiles),
        "--output-dir",
        str(task_c_dir),
        "--target-lang",
        args.target_lang,
        "--backend",
        args.translation_backend,
        "--glossary",
        args.glossary,
        "--device",
        args.device,
    ]
    if args.api_model:
        translate_cmd.extend(["--api-model", args.api_model])
    _run_cli(translate_cmd)
    task_c_translation = task_c_dir / "voice" / f"translation.{args.target_lang}.json"

    profiles_payload = json.loads(task_b_profiles.read_text(encoding="utf-8"))
    translation_payload = json.loads(task_c_translation.read_text(encoding="utf-8"))
    speaker_ids = pick_task_d_speaker_ids(
        profiles_payload=profiles_payload,
        translation_payload=translation_payload,
        limit=1,
    )
    if not speaker_ids and not args.speaker_id:
        raise ValueError("No suitable speaker found for Task D")
    speaker_id = args.speaker_id or speaker_ids[0]
    selected_segment_ids = pick_segment_ids_for_speaker(
        translation_payload=translation_payload,
        speaker_id=speaker_id,
        limit=args.max_segments,
    )

    synthesize_cmd = [
        "synthesize-speaker",
        "--translation",
        str(task_c_translation),
        "--profiles",
        str(task_b_profiles),
        "--speaker-id",
        speaker_id,
        "--output-dir",
        str(task_d_dir),
        "--backend",
        args.tts_backend,
        "--device",
        args.device,
    ]
    if selected_segment_ids:
        for segment_id in selected_segment_ids:
            synthesize_cmd.extend(["--segment-id", segment_id])
    elif args.max_segments is not None:
        synthesize_cmd.extend(["--max-segments", str(args.max_segments)])
    _run_cli(synthesize_cmd)

    task_d_bundle = task_d_dir / "voice" / speaker_id
    task_d_report = task_d_bundle / f"speaker_segments.{args.target_lang}.json"
    task_d_demo = task_d_bundle / f"speaker_demo.{args.target_lang}.wav"
    task_d_manifest = task_d_bundle / "task-d-manifest.json"

    print(f"stage1_voice={voice_path}")
    print(f"task_a_segments={task_a_segments}")
    print(f"task_b_profiles={task_b_profiles}")
    print(f"task_c_translation={task_c_translation}")
    print(f"task_d_report={task_d_report}")
    if task_d_demo.exists():
        print(f"task_d_demo={task_d_demo}")
    print(f"task_d_manifest={task_d_manifest}")
    if selected_segment_ids:
        print(f"task_d_segment_ids={','.join(selected_segment_ids)}")
    return 0


def _run_cli(args: list[str]) -> None:
    cmd = [str(_cli_executable()), *args]
    subprocess.run(cmd, check=True, env=_cli_env())


def _cli_executable() -> Path:
    return Path(sys.executable).with_name("video-voice-separate")


def _cli_env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")
    env.setdefault("HF_HUB_DISABLE_XET", "1")
    env.setdefault("HF_HUB_ENABLE_HF_TRANSFER", "0")
    return env


if __name__ == "__main__":
    raise SystemExit(main())
