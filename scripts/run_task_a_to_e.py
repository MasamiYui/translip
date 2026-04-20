from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from translip.dubbing.planning import (
    pick_segment_ids_for_speaker,
    pick_task_d_speaker_ids,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run stage 1 and tasks A-E in sequence.")
    parser.add_argument("--input", required=True, help="Input video or audio path")
    parser.add_argument("--output-root", default="tmp/e2e-task-a-to-e", help="Output root directory")
    parser.add_argument("--target-lang", default="en", help="Task C/D/E target language")
    parser.add_argument(
        "--translation-backend",
        default="local-m2m100",
        choices=["local-m2m100", "siliconflow"],
        help="Task C translation backend",
    )
    parser.add_argument(
        "--tts-backend",
        default="moss-tts-nano-onnx",
        choices=["moss-tts-nano-onnx", "qwen3tts"],
    )
    parser.add_argument("--glossary", default="config/glossary.example.json", help="Optional glossary path")
    parser.add_argument("--device", default="auto", choices=["auto", "cpu", "cuda", "mps"])
    parser.add_argument("--api-model", default=None, help="Optional SiliconFlow model override")
    parser.add_argument(
        "--speaker-limit",
        type=int,
        default=2,
        help="How many speakers to synthesize for Task D; <=0 means all ranked speakers",
    )
    parser.add_argument(
        "--segments-per-speaker",
        type=int,
        default=3,
        help="How many segments to synthesize per speaker; <=0 means all usable segments",
    )
    parser.add_argument(
        "--fit-policy",
        default="conservative",
        choices=["conservative", "high_quality"],
    )
    parser.add_argument(
        "--fit-backend",
        default="atempo",
        choices=["atempo", "rubberband"],
    )
    parser.add_argument(
        "--mix-profile",
        default="preview",
        choices=["preview", "enhanced"],
    )
    parser.add_argument(
        "--ducking-mode",
        default="static",
        choices=["static", "sidechain"],
    )
    parser.add_argument("--output-sample-rate", type=int, default=24_000)
    parser.add_argument("--background-gain-db", type=float, default=-8.0)
    parser.add_argument("--window-ducking-db", type=float, default=-3.0)
    parser.add_argument("--max-compress-ratio", type=float, default=1.45)
    parser.add_argument("--preview-format", default="wav", choices=["wav", "mp3"])
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
    task_e_dir = output_root / "task-e"
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
    background_path = source_bundle / "background.mp3"

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
    speaker_limit = max(args.speaker_limit, 0)
    profile_count = len(profiles_payload.get("profiles", []))
    candidate_limit = profile_count if speaker_limit == 0 else min(profile_count, max(speaker_limit * 3, speaker_limit))
    ranked_speaker_ids = pick_task_d_speaker_ids(
        profiles_payload=profiles_payload,
        translation_payload=translation_payload,
        limit=candidate_limit,
    )
    if not ranked_speaker_ids:
        raise ValueError("No suitable speakers found for Task D/Task E pipeline run")

    task_d_reports: list[Path] = []
    selected_segment_map: dict[str, list[str] | None] = {}
    for speaker_id in ranked_speaker_ids:
        segment_limit = None if args.segments_per_speaker <= 0 else args.segments_per_speaker
        selected_segment_ids = pick_segment_ids_for_speaker(
            translation_payload=translation_payload,
            speaker_id=speaker_id,
            limit=segment_limit,
        )
        selected_segment_map[speaker_id] = selected_segment_ids

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
        _run_cli(synthesize_cmd)

        report_path = task_d_dir / "voice" / speaker_id / f"speaker_segments.{args.target_lang}.json"
        report_payload = json.loads(report_path.read_text(encoding="utf-8"))
        if _count_renderable_task_d_segments(report_payload) <= 0:
            continue
        task_d_reports.append(report_path)
        if speaker_limit and len(task_d_reports) >= speaker_limit:
            break

    if not task_d_reports:
        raise ValueError("Task D did not produce any renderable segments for Task E")

    render_cmd = [
        "render-dub",
        "--background",
        str(background_path),
        "--segments",
        str(task_a_segments),
        "--translation",
        str(task_c_translation),
        "--output-dir",
        str(task_e_dir),
        "--target-lang",
        args.target_lang,
        "--fit-policy",
        args.fit_policy,
        "--fit-backend",
        args.fit_backend,
        "--mix-profile",
        args.mix_profile,
        "--ducking-mode",
        args.ducking_mode,
        "--output-sample-rate",
        str(args.output_sample_rate),
        "--background-gain-db",
        str(args.background_gain_db),
        "--window-ducking-db",
        str(args.window_ducking_db),
        "--max-compress-ratio",
        str(args.max_compress_ratio),
        "--preview-format",
        args.preview_format,
    ]
    for report_path in task_d_reports:
        render_cmd.extend(["--task-d-report", str(report_path)])
    _run_cli(render_cmd)

    task_e_bundle = task_e_dir / "voice"
    preview_suffix = args.preview_format

    print(f"stage1_voice={voice_path}")
    print(f"stage1_background={background_path}")
    print(f"task_a_segments={task_a_segments}")
    print(f"task_b_profiles={task_b_profiles}")
    print(f"task_c_translation={task_c_translation}")
    print(f"task_d_reports={','.join(str(path) for path in task_d_reports)}")
    for speaker_id, segment_ids in selected_segment_map.items():
        if segment_ids:
            print(f"task_d_segments_{speaker_id}={','.join(segment_ids)}")
    print(f"task_e_dub_voice={task_e_bundle / f'dub_voice.{args.target_lang}.wav'}")
    print(f"task_e_preview_mix_wav={task_e_bundle / f'preview_mix.{args.target_lang}.wav'}")
    if preview_suffix != "wav":
        print(f"task_e_preview_mix_extra={task_e_bundle / f'preview_mix.{args.target_lang}.{preview_suffix}'}")
    print(f"task_e_timeline={task_e_bundle / f'timeline.{args.target_lang}.json'}")
    print(f"task_e_mix_report={task_e_bundle / f'mix_report.{args.target_lang}.json'}")
    print(f"task_e_manifest={task_e_bundle / 'task-e-manifest.json'}")
    return 0


def _count_renderable_task_d_segments(payload: dict[str, object]) -> int:
    count = 0
    for row in payload.get("segments", []):
        if not isinstance(row, dict):
            continue
        if str(row.get("overall_status") or "") != "failed":
            count += 1
    return count


def _run_cli(args: list[str]) -> None:
    cmd = [str(_cli_executable()), *args]
    subprocess.run(cmd, check=True, env=_cli_env())


def _cli_executable() -> Path:
    return Path(sys.executable).with_name("translip")


def _cli_env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")
    env.setdefault("HF_HUB_DISABLE_XET", "1")
    env.setdefault("HF_HUB_ENABLE_HF_TRANSFER", "0")
    return env


if __name__ == "__main__":
    raise SystemExit(main())
