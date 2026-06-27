#!/usr/bin/env python3
"""In-tree entry point for the commentary pipeline stages.

Two tasks, both writing the artifact + ``<task>-manifest.json`` contract the
orchestrator's cache expects (manifest ``status: "succeeded"`` + artifacts exist):

    --task script : segments.json [+ visual_context.json] -> commentary.json
    --task render : commentary.json + source video        -> recap.mp4 (+ report)

Invoke as a module so it works regardless of install mode:

    python -m translip.commentary.extract --task script \
        --segments segments.zh.json --output-dir commentary-script/ [--visual-context vc.json]
    python -m translip.commentary.extract --task render \
        --commentary commentary.json --input video.mp4 --output-dir commentary-render/

The render task reuses the pure planner/command builders from
``translip.commentary.render`` (same core the atomic commentary-render tool uses)
and synthesizes narration with the local qwen3tts backend.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from .chain import CommentaryOptions, generate_commentary_script
from .inputs import build_story_document, load_segments, load_visual_units
from .render import build_clip_command, build_concat_command, plan_render, write_concat_list
from .voices import DEFAULT_NARRATOR_VOICE, resolve_narrator_reference

# Parsed by orchestration/commentary_bridge.py to drive progress bars. Kept as a
# literal there too so the bridge stays free of this module at import time.
PROGRESS_PREFIX = "__COMMENTARY_PROGRESS__"

_CRF = 20
_PRESET = "medium"


def _progress(percent: float, message: str) -> None:
    print(f"{PROGRESS_PREFIX}\t{int(percent)}\t{message}", flush=True)


def _write_manifest(path: Path, *, node: str, task: str, artifacts: list[str], params: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(
            {"node": node, "task": task, "status": "succeeded", "artifacts": artifacts, "params": params},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


# --- script task -------------------------------------------------------------

def run_script(
    *,
    segments_path: Path,
    output_dir: Path,
    visual_context_path: Path | None,
    style: str,
    genre: str,
    language: str,
    original_sound_ratio: int,
    model: str | None,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    _progress(5.0, "loading transcript")
    segments = load_segments(segments_path)
    if not segments:
        raise SystemExit("segments JSON is empty or missing 'segments'; cannot write a commentary script.")
    visual_units = (
        load_visual_units(visual_context_path)
        if visual_context_path is not None and visual_context_path.exists()
        else []
    )
    story = build_story_document(segments, visual_units)
    options = CommentaryOptions(
        style=style,
        genre=genre,
        language=language,
        original_sound_ratio=int(original_sound_ratio),
        model=model,
    )
    _progress(20.0, "writing commentary script")
    script = generate_commentary_script(
        story=story,
        options=options,
        on_progress=lambda pct, step=None: _progress(20.0 + 0.7 * float(pct), step or "writing"),
    )
    commentary_path = output_dir / "commentary.json"
    commentary_path.write_text(
        json.dumps(
            script.to_payload(
                source={
                    "segment_count": story.segment_count,
                    "visual_unit_count": story.visual_unit_count,
                    "duration_sec": story.duration_sec,
                    "truncated": story.truncated,
                }
            ),
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    manifest_path = output_dir / "commentary-script-manifest.json"
    _write_manifest(
        manifest_path,
        node="commentary-script",
        task="script",
        artifacts=[commentary_path.name, manifest_path.name],
        params={"style": style, "genre": genre, "language": language, "original_sound_ratio": int(original_sound_ratio)},
    )
    _progress(100.0, "commentary script ready")
    return manifest_path


# --- render task -------------------------------------------------------------

def _make_narrator_backend():
    """qwen3tts is clone-only — synth narration off the Base model + a reference
    voice (x-vector mode, so no reference transcript is needed). Lazily imported so
    `--help` / the script task never load the TTS stack."""
    from ..dubbing.qwen_tts_backend import QwenTTSBackend

    return QwenTTSBackend(requested_device="auto", clone_mode="xvec")


def _synthesize_narration(
    backend, reference_path: Path, text: str, language: str, output_path: Path
) -> float:
    """Clone-synthesize one narration line off the narrator reference; returns its duration (sec)."""
    from ..dubbing.backend import ReferencePackage, SynthSegmentInput

    reference = ReferencePackage(
        speaker_id="narrator",
        profile_id="narrator",
        original_audio_path=reference_path,
        prepared_audio_path=reference_path,
        text="",  # ignored in x-vector clone mode
        duration_sec=0.0,
        score=0.0,
        selection_reason="commentary-narrator",
    )
    segment = SynthSegmentInput(
        segment_id="commentary",
        speaker_id="narrator",
        target_lang=language if language != "auto" else "zh",
        target_text=text,
        source_duration_sec=max(0.8, len(text) / 12.0),
        duration_budget_sec=max(0.8, len(text) / 10.0),
    )
    return backend.synthesize(reference=reference, segment=segment, output_path=output_path).generated_duration_sec


def _run_ffmpeg(command: list[str]) -> None:
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        tail = (result.stderr or "").strip()[-800:]
        raise RuntimeError(f"ffmpeg failed (exit {result.returncode}): {tail}")


def run_render(
    *,
    commentary_path: Path,
    input_path: Path,
    output_dir: Path,
    backend: str,
    language: str | None,
    original_gain_db: float,
    narrator_voice: str | None = None,
    reference_audio_path: Path | None = None,
) -> Path:
    from ..utils.ffmpeg import ffmpeg_binary, probe_media, probe_video_resolution

    output_dir.mkdir(parents=True, exist_ok=True)
    work_dir = output_dir / "work"
    work_dir.mkdir(parents=True, exist_ok=True)

    payload = json.loads(commentary_path.read_text(encoding="utf-8"))
    items = [item for item in (payload.get("items") or []) if isinstance(item, dict)]
    if not items:
        raise SystemExit("commentary.json has no items; nothing to render.")
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    narration_language = language or meta.get("narration_language") or "zh"

    media = probe_media(input_path)
    if not media.audio_stream_count:
        raise SystemExit("source video has no audio track; commentary render needs the original audio.")
    source_duration = float(media.duration_sec or 0.0)
    if source_duration <= 0:
        raise SystemExit("could not read source video duration.")
    width, height = probe_video_resolution(input_path)

    _progress(5.0, "synthesizing narration")
    ost0 = [it for it in items if int(it.get("ost", 0) or 0) == 0 and str(it.get("narration") or "").strip()]
    narration_durations: dict[int, float] = {}
    narration_paths: dict[int, Path] = {}
    if ost0:
        # An explicit uploaded reference (CLI --reference) wins; otherwise the
        # narrator-voice selector (built-in id / "source" / path) decides. The
        # default is a built-in designed voice — never borrow the cast's voice.
        selector = str(reference_audio_path) if reference_audio_path else narrator_voice
        reference_path = resolve_narrator_reference(
            selector,
            language=narration_language,
            work_dir=work_dir,
            source_path=input_path,
            source_duration=source_duration,
        )
        narrator_backend = _make_narrator_backend()
        for index, item in enumerate(ost0):
            item_id = int(item["id"])
            narration_wav = work_dir / f"narration_{item_id}.wav"
            narration_durations[item_id] = _synthesize_narration(
                narrator_backend, reference_path, str(item["narration"]), narration_language, narration_wav
            )
            narration_paths[item_id] = narration_wav
            _progress(5.0 + 45.0 * (index + 1) / len(ost0), "synthesizing narration")

    specs = plan_render(items, narration_durations=narration_durations, source_duration=source_duration)
    if not specs:
        raise SystemExit("no renderable clips (check commentary src ranges against the video duration).")

    ffmpeg = ffmpeg_binary()
    clip_paths: list[Path] = []
    for spec in specs:
        clip_path = work_dir / f"clip_{spec.index:04d}.mp4"
        _run_ffmpeg(
            build_clip_command(
                ffmpeg=ffmpeg,
                spec=spec,
                source_path=input_path,
                narration_path=narration_paths.get(spec.item_id),
                output_path=clip_path,
                width=width,
                height=height,
                crf=_CRF,
                preset=_PRESET,
                original_gain_db=float(original_gain_db),
            )
        )
        clip_paths.append(clip_path)
        _progress(50.0 + 40.0 * (spec.index + 1) / len(specs), "rendering clips")

    _progress(92.0, "assembling recap")
    recap_path = output_dir / "recap.mp4"
    concat_list = write_concat_list(clip_paths, work_dir / "concat.txt")
    _run_ffmpeg(build_concat_command(ffmpeg=ffmpeg, list_path=concat_list, output_path=recap_path))
    if not recap_path.exists() or recap_path.stat().st_size == 0:
        raise RuntimeError("concat succeeded but produced no recap video.")

    report = {
        "backend": backend,
        "narrator_voice": narrator_voice or DEFAULT_NARRATOR_VOICE,
        "narration_language": narration_language,
        "timeline_duration_sec": round(sum(spec.av_duration for spec in specs), 3),
        "clip_count": len(specs),
        "ost0_count": sum(1 for s in specs if s.ost == 0),
        "ost1_count": sum(1 for s in specs if s.ost == 1),
        "clips": [
            {
                "index": spec.index,
                "item_id": spec.item_id,
                "ost": spec.ost,
                "src_start": spec.src_start,
                "take_duration": spec.take_duration,
                "av_duration": spec.av_duration,
                "narration_duration_sec": narration_durations.get(spec.item_id),
            }
            for spec in specs
        ],
    }
    report_path = output_dir / "commentary_render_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest_path = output_dir / "commentary-render-manifest.json"
    _write_manifest(
        manifest_path,
        node="commentary-render",
        task="render",
        artifacts=[recap_path.name, report_path.name, manifest_path.name],
        params={"backend": backend, "narrator_voice": narrator_voice or DEFAULT_NARRATOR_VOICE, "narration_language": narration_language, "original_gain_db": float(original_gain_db)},
    )
    _progress(100.0, "recap ready")
    return manifest_path


# --- CLI ---------------------------------------------------------------------

def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="translip in-tree commentary stage")
    parser.add_argument("--task", required=True, choices=["script", "render"])
    parser.add_argument("--output-dir", required=True)
    # script
    parser.add_argument("--segments", default=None, help="transcript segments JSON (task=script)")
    parser.add_argument("--visual-context", default=None, help="optional visual_context.json (task=script)")
    parser.add_argument("--style", default="plot_recap")
    parser.add_argument("--genre", default="剧情")
    parser.add_argument("--original-sound-ratio", type=int, default=20)
    parser.add_argument("--model", default=None, help="LLM model override (task=script)")
    # render
    parser.add_argument("--commentary", default=None, help="commentary.json (task=render)")
    parser.add_argument("--input", default=None, help="source video (task=render)")
    parser.add_argument("--backend", default="qwen3tts", help="TTS backend (task=render)")
    parser.add_argument("--narrator-voice", default=None, help="built-in narrator voice id, 'source' (borrow from video), or a reference audio path (task=render); defaults to the built-in default voice")
    parser.add_argument("--reference", default=None, help="explicit narrator reference audio path (task=render); overrides --narrator-voice when given")
    parser.add_argument("--original-gain-db", type=float, default=-15.0)
    # shared
    parser.add_argument("--language", default="zh", help="narration language")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.task == "script":
        if not args.segments:
            raise SystemExit("--segments is required for --task script")
        run_script(
            segments_path=Path(args.segments),
            output_dir=Path(args.output_dir),
            visual_context_path=Path(args.visual_context) if args.visual_context else None,
            style=args.style,
            genre=args.genre,
            language=args.language,
            original_sound_ratio=int(args.original_sound_ratio),
            model=args.model,
        )
    else:
        if not args.commentary or not args.input:
            raise SystemExit("--commentary and --input are required for --task render")
        run_render(
            commentary_path=Path(args.commentary),
            input_path=Path(args.input),
            output_dir=Path(args.output_dir),
            backend=args.backend,
            language=args.language,
            original_gain_db=float(args.original_gain_db),
            narrator_voice=args.narrator_voice,
            reference_audio_path=Path(args.reference) if args.reference else None,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
