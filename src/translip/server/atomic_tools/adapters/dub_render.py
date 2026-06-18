"""Composite "dub" atomic tool: per-segment TTS → timeline-fit → sidechain mix.

The single-blob ``tts`` tool synthesizes one chunk of text with no timing, so it
can't produce a watchable dub. This tool closes that gap by chaining, in one job:

1. read the translation JSON (the per-segment timeline: segment_id / speaker_id /
   start / end / duration / target_text — produced by the ``translation`` tool),
2. synthesize each segment's target line with the shared ``generate_speech``
   helper (the same backend the ``tts`` tool uses),
3. assemble a minimal Task-D-shaped report + a timing anchor file — exactly the
   contract ``rendering.render_dub`` consumes — and run the proven timeline-fit /
   sidechain-mix renderer over them,
4. optionally mux the resulting mix back onto the source video as a finished MP4.

It deliberately reuses ``render_dub`` rather than reimplementing fitting, so the
chipmunk-speed / tail-trim / overlap handling stays in one place. It does NOT use
the heavyweight per-speaker ``synthesize_speaker`` (speaker profiles / voice bank
/ QA retries) — references here are a single optional upload cloned for every
speaker, which is the right granularity for an atomic, registry-free job.
"""

from __future__ import annotations

import json
from pathlib import Path

from ....rendering.runner import render_dub
from ....types import RenderDubRequest
from ....utils.ffmpeg import mux_video_with_audio
from ..registry import ToolSpec, register_tool
from ..schemas import DubRenderToolRequest
from . import ToolAdapter
from .tts import generate_speech


class DubRenderAdapter(ToolAdapter):
    def validate_params(self, params: dict) -> dict:
        return DubRenderToolRequest(**params).model_dump()

    def run(self, params, input_dir, output_dir, on_progress):
        translation_path = self.first_input(input_dir, "translation_file")
        background_path = self.first_input(input_dir, "background_file")
        reference_audio_path = (
            self.first_input(input_dir, "reference_audio_file")
            if params.get("reference_audio_file_id")
            else None
        )
        video_path = (
            self.first_input(input_dir, "video_file") if params.get("video_file_id") else None
        )
        output_dir.mkdir(parents=True, exist_ok=True)

        translation_payload = json.loads(translation_path.read_text(encoding="utf-8"))
        segments = [row for row in translation_payload.get("segments", []) if isinstance(row, dict)]
        if not segments:
            raise ValueError("Translation JSON has no segments to dub.")
        target_lang = params.get("target_lang", "auto")
        if target_lang == "auto":
            target_lang = str(translation_payload.get("backend", {}).get("target_lang") or "en")
        backend = params.get("backend", "qwen3tts")

        # 1. Synthesize each line and record a Task-D-shaped row for the renderer.
        synth_dir = output_dir / "segments"
        synth_dir.mkdir(parents=True, exist_ok=True)
        report_segments: list[dict] = []
        anchor_segments: list[dict] = []
        total = len(segments)
        for index, row in enumerate(segments):
            segment_id = str(row.get("segment_id") or f"seg-{index:04d}")
            text = str(row.get("dubbing_text") or row.get("target_text") or "").strip()
            start = float(row.get("start") or 0.0)
            end = float(row.get("end") or start)
            source_duration = float(row.get("duration") or max(0.0, end - start))
            anchor_segments.append({"segment_id": segment_id, "start": start, "end": end, "duration": source_duration})
            if not text:
                continue
            segment_wav = synth_dir / f"{_safe(segment_id)}.wav"
            metadata = generate_speech(
                text=text,
                language=target_lang,
                backend=backend,
                reference_audio_path=reference_audio_path,
                output_path=segment_wav,
            )
            report_segments.append(
                {
                    "segment_id": segment_id,
                    "speaker_id": str(row.get("speaker_id") or ""),
                    "target_text": text,
                    "audio_path": str(segment_wav.resolve()),
                    "generated_duration_sec": float(metadata["duration_sec"]),
                    "source_duration_sec": source_duration,
                    "overall_status": "passed",
                    "duration_status": "ok",
                    "speaker_status": "unknown",
                    "intelligibility_status": "unknown",
                    "speaker_similarity": None,
                    "text_similarity": None,
                    "qa_flags": [str(flag) for flag in row.get("qa_flags", [])],
                }
            )
            on_progress(5.0 + 70.0 * (index + 1) / total, f"synthesizing {index + 1}/{total}")

        if not report_segments:
            raise ValueError("No non-empty translation lines to synthesize.")

        # 2. Write the renderer's three inputs: timing anchor, the per-segment
        #    report, and the (already on disk) translation JSON.
        anchor_path = output_dir / "_dub_inputs" / "segments.json"
        report_path = output_dir / "_dub_inputs" / f"speaker_segments.{target_lang}.json"
        self.write_json(anchor_path, {"segments": anchor_segments})
        self.write_json(
            report_path,
            {"backend": {"target_lang": target_lang}, "segments": report_segments},
        )

        # 3. Timeline-fit + sidechain-mix via the proven render stage.
        on_progress(78.0, "rendering")
        render_result = render_dub(
            RenderDubRequest(
                background_path=background_path,
                segments_path=anchor_path,
                translation_path=translation_path,
                task_d_report_paths=[report_path],
                output_dir=output_dir / "_dub_render",
                target_lang=target_lang,
                ducking_mode=params.get("ducking_mode", "static"),
                background_gain_db=float(params.get("background_gain_db", -8.0)),
            )
        )
        mix_path = self.copy_output(
            render_result.artifacts.preview_mix_wav_path, output_dir, f"dub_mix.{target_lang}.wav"
        )

        result = {
            "mixed_audio_file": mix_path.name,
            "target_lang": target_lang,
            "dubbed_segments": len(report_segments),
            "total_segments": total,
        }

        # 4. Optional: deliver a finished video with the dub mixed in.
        if video_path is not None:
            on_progress(95.0, "muxing")
            dubbed_video = output_dir / "dubbed.mp4"
            mux_video_with_audio(
                input_video_path=video_path,
                input_audio_path=mix_path,
                output_path=dubbed_video,
                audio_language=target_lang,
            )
            result["output_file"] = dubbed_video.name

        on_progress(99.0, "finalizing")
        return result


def _safe(segment_id: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in segment_id) or "segment"


register_tool(
    ToolSpec(
        tool_id="dub-render",
        name_zh="配音渲染（时间轴对齐）",
        name_en="Dub Render (Timeline-fit)",
        description_zh="按翻译时间轴逐段合成配音，对齐时间轴并与背景音 sidechain 混音，可选合并回视频",
        description_en="Synthesize per-segment dub on the translation timeline, fit to timing, sidechain-mix with background, optionally mux back onto the video",
        category="speech",
        icon="AudioLines",
        accept_formats=[".json", ".wav", ".mp3", ".flac", ".m4a", ".mp4", ".mkv", ".mov"],
        max_file_size_mb=2000,
        max_files=4,
        heavy=True,
    ),
    DubRenderAdapter,
)
