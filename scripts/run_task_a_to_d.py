from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from video_voice_separate.dubbing.reference import select_reference_candidates
from video_voice_separate.dubbing.runner import synthesize_speaker
from video_voice_separate.pipeline.runner import separate_file
from video_voice_separate.speakers.runner import build_speaker_registry
from video_voice_separate.translation.runner import translate_script
from video_voice_separate.transcription.runner import transcribe_file
from video_voice_separate.types import (
    DubbingRequest,
    SeparationRequest,
    SpeakerRegistryRequest,
    TranscriptionRequest,
    TranslationRequest,
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
    parser.add_argument("--tts-backend", default="f5tts", choices=["f5tts", "openvoice"])
    parser.add_argument("--speaker-id", default=None, help="Optional speaker id override for Task D")
    parser.add_argument("--glossary", default="config/glossary.example.json", help="Optional glossary path")
    parser.add_argument("--device", default="auto", choices=["auto", "cpu", "cuda", "mps"])
    parser.add_argument("--api-model", default=None, help="Optional SiliconFlow model override")
    parser.add_argument("--max-segments", type=int, default=None, help="Optional Task D segment cap")
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

    speaker_id = args.speaker_id or _pick_task_d_speaker(
        profiles_path=registry.artifacts.profiles_path,
        translation_path=translation.artifacts.translation_json_path,
    )
    selected_segment_ids = _pick_segment_ids(
        translation_path=translation.artifacts.translation_json_path,
        speaker_id=speaker_id,
        limit=args.max_segments,
    )
    dubbing = synthesize_speaker(
        DubbingRequest(
            translation_path=translation.artifacts.translation_json_path,
            profiles_path=registry.artifacts.profiles_path,
            output_dir=output_root / "task-d",
            speaker_id=speaker_id,
            backend=args.tts_backend,
            device=args.device,
            segment_ids=selected_segment_ids,
            max_segments=args.max_segments if selected_segment_ids is None else None,
        )
    )

    print(f"stage1_voice={separation.artifacts.voice_path}")
    print(f"task_a_segments={transcription.artifacts.segments_json_path}")
    print(f"task_b_profiles={registry.artifacts.profiles_path}")
    print(f"task_c_translation={translation.artifacts.translation_json_path}")
    print(f"task_d_report={dubbing.artifacts.report_path}")
    if dubbing.artifacts.demo_audio_path:
        print(f"task_d_demo={dubbing.artifacts.demo_audio_path}")
    print(f"task_d_manifest={dubbing.artifacts.manifest_path}")
    if selected_segment_ids:
        print(f"task_d_segment_ids={','.join(selected_segment_ids)}")
    return 0


def _pick_task_d_speaker(*, profiles_path: Path, translation_path: Path) -> str:
    payload = json.loads(Path(profiles_path).read_text(encoding="utf-8"))
    profiles = [profile for profile in payload.get("profiles", []) if isinstance(profile, dict)]
    if not profiles:
        raise ValueError("No speaker profiles available for Task D")

    translation_payload = json.loads(Path(translation_path).read_text(encoding="utf-8"))
    usable_counts: dict[str, int] = defaultdict(int)
    short_counts: dict[str, int] = defaultdict(int)

    for row in translation_payload.get("segments", []):
        if not isinstance(row, dict):
            continue
        speaker_id = str(row.get("speaker_id") or "")
        duration_sec = float(row.get("duration") or 0.0)
        flags = {str(flag) for flag in row.get("qa_flags", [])}
        if _is_usable_task_d_segment(duration_sec=duration_sec, qa_flags=flags):
            usable_counts[speaker_id] += 1
        if 1.0 <= duration_sec <= 4.0 and "too_short_source" not in flags:
            short_counts[speaker_id] += 1

    best_tuple: tuple[int, int, float, float, str] | None = None
    for profile in profiles:
        speaker_id = str(profile.get("speaker_id") or "")
        if not speaker_id or usable_counts.get(speaker_id, 0) <= 0:
            continue
        try:
            top_reference = select_reference_candidates(
                profiles_payload=payload,
                speaker_id=speaker_id,
            )[0]
        except ValueError:
            continue
        candidate_tuple = (
            usable_counts.get(speaker_id, 0),
            short_counts.get(speaker_id, 0),
            float(top_reference.score),
            float(profile.get("total_speech_sec") or 0.0),
            speaker_id,
        )
        if best_tuple is None or candidate_tuple > best_tuple:
            best_tuple = candidate_tuple

    if best_tuple is None:
        raise ValueError("No suitable speaker found for Task D")
    return best_tuple[-1]


def _pick_segment_ids(
    *,
    translation_path: Path,
    speaker_id: str,
    limit: int | None,
) -> list[str] | None:
    if limit is None:
        return None

    payload = json.loads(Path(translation_path).read_text(encoding="utf-8"))
    rows = [
        row
        for row in payload.get("segments", [])
        if isinstance(row, dict) and str(row.get("speaker_id")) == speaker_id
    ]
    rows = sorted(rows, key=lambda row: (float(row.get("start") or 0.0), str(row.get("segment_id") or "")))
    preferred = [
        row for row in rows if _is_preferred_task_d_segment(float(row.get("duration") or 0.0), row.get("qa_flags", []))
    ]
    fallback = [
        row
        for row in rows
        if _is_usable_task_d_segment(
            duration_sec=float(row.get("duration") or 0.0),
            qa_flags={str(flag) for flag in row.get("qa_flags", [])},
        )
    ]
    selected: list[str] = []
    for pool in (preferred, fallback, rows):
        for row in pool:
            segment_id = str(row.get("segment_id") or "")
            if not segment_id or segment_id in selected:
                continue
            selected.append(segment_id)
            if len(selected) >= limit:
                return selected
    return selected or None


def _is_usable_task_d_segment(*, duration_sec: float, qa_flags: set[str]) -> bool:
    if duration_sec < 1.0 or duration_sec > 6.0:
        return False
    if "too_short_source" in qa_flags:
        return False
    return True


def _is_preferred_task_d_segment(duration_sec: float, qa_flags: list[str] | set[str]) -> bool:
    normalized_flags = {str(flag) for flag in qa_flags}
    if not _is_usable_task_d_segment(duration_sec=duration_sec, qa_flags=normalized_flags):
        return False
    if "duration_risky" in normalized_flags:
        return False
    return 1.5 <= duration_sec <= 4.5


if __name__ == "__main__":
    raise SystemExit(main())
