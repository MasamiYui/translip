from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from ....commentary.render import (
    build_clip_command,
    build_concat_command,
    plan_render,
    write_concat_list,
)
from ....orchestration.subprocess_runner import StageSubprocessError, run_stage_command
from ....utils.ffmpeg import ffmpeg_binary, probe_media, probe_video_resolution
from ..cancellation import cancel_checker
from ..ffmpeg_progress import describe_ffmpeg_failure
from ..registry import ToolSpec, register_tool
from ..schemas import CommentaryRenderToolRequest
from . import ToolAdapter
from .tts import generate_speech

_CRF = 20
_PRESET = "medium"


def _load_items(commentary_path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    payload = json.loads(commentary_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("commentary.json 格式不正确（应为对象）。")
    items = payload.get("items")
    if not isinstance(items, list) or not items:
        raise RuntimeError("commentary.json 缺少 items 或为空，无法渲染解说视频。")
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    return [item for item in items if isinstance(item, dict)], meta


class CommentaryRenderAdapter(ToolAdapter):
    """Step 2 (assembly): a reviewed ``commentary.json`` + the source video → a
    finished OST-interleaved recap MP4.

    OST=0 items are voiced (TTS) and laid over the ducked original; OST=1 items
    keep the original audio. Every clip is normalised to one profile so the final
    concat is a stream-copy. The heavy timeline math + ffmpeg argv live in
    ``translip.commentary.render`` (pure, tested); this only orchestrates I/O.
    """

    def validate_params(self, params: dict) -> dict:
        return CommentaryRenderToolRequest(**params).model_dump()

    def run(self, params, input_dir, output_dir, on_progress):
        on_progress(2.0, "loading_inputs")
        commentary_path = self.first_input(input_dir, "commentary_file")
        video_path = self.first_input(input_dir, "video_file")
        reference_path = (
            self.first_input(input_dir, "reference_audio_file")
            if params.get("reference_audio_file_id")
            else None
        )
        items, meta = _load_items(commentary_path)

        media = probe_media(video_path)
        if not media.audio_stream_count:
            raise RuntimeError(
                "源视频没有音频轨。解说渲染需要原声（OST=1 保留原声 / OST=0 压混原声）。"
            )
        source_duration = float(media.duration_sec or 0.0)
        if source_duration <= 0:
            raise RuntimeError("无法读取源视频时长。")
        width, height = probe_video_resolution(video_path)

        backend = params.get("backend", "qwen3tts")
        language = params.get("narration_language") or meta.get("narration_language") or "zh"
        output_dir.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory(prefix="commentary-render-") as work_str:
            work = Path(work_str)

            # --- 1. synthesize narration for OST=0 items -------------------
            ost0 = [it for it in items if int(it.get("ost", 0) or 0) == 0 and str(it.get("narration") or "").strip()]
            narration_durations: dict[int, float] = {}
            narration_paths: dict[int, Path] = {}
            for index, item in enumerate(ost0):
                item_id = int(item["id"])
                narration_wav = work / f"narration_{item_id}.wav"
                tts_meta = generate_speech(
                    text=str(item["narration"]),
                    language=language,
                    backend=backend,
                    reference_audio_path=reference_path,
                    output_path=narration_wav,
                )
                narration_durations[item_id] = float(tts_meta["duration_sec"])
                narration_paths[item_id] = narration_wav
                on_progress(5.0 + 45.0 * (index + 1) / len(ost0), "synthesizing_narration")

            # --- 2. resolve the timeline ----------------------------------
            specs = plan_render(
                items, narration_durations=narration_durations, source_duration=source_duration
            )
            if not specs:
                raise RuntimeError(
                    "没有可渲染的片段（检查 commentary.json 的 src 时间区间是否落在视频时长内）。"
                )

            should_cancel = cancel_checker(on_progress)
            ffmpeg = ffmpeg_binary()

            # --- 3. render each clip to a normalised intermediate ---------
            clip_paths: list[Path] = []
            for spec in specs:
                clip_path = work / f"clip_{spec.index:04d}.mp4"
                command = build_clip_command(
                    ffmpeg=ffmpeg,
                    spec=spec,
                    source_path=video_path,
                    narration_path=narration_paths.get(spec.item_id),
                    output_path=clip_path,
                    width=width,
                    height=height,
                    crf=_CRF,
                    preset=_PRESET,
                    original_gain_db=float(params.get("original_gain_db", -15.0)),
                )
                self._run_ffmpeg(command, work / f"clip_{spec.index:04d}.log", should_cancel)
                clip_paths.append(clip_path)
                on_progress(50.0 + 40.0 * (spec.index + 1) / len(specs), "rendering_clips")

            # --- 4. concat into the final recap ---------------------------
            on_progress(92.0, "assembling")
            recap_path = output_dir / "recap.mp4"
            concat_list = write_concat_list(clip_paths, work / "concat.txt")
            self._run_ffmpeg(
                build_concat_command(ffmpeg=ffmpeg, list_path=concat_list, output_path=recap_path),
                output_dir / "ffmpeg-concat.log",
                should_cancel,
            )

            if not recap_path.exists() or recap_path.stat().st_size == 0:
                raise RuntimeError("拼接成功退出但未产出视频文件，请检查 commentary.json 与源视频。")

            report = self._build_report(specs, narration_durations, meta, backend, language)
            report_path = self.write_json(output_dir / "commentary_render_report.json", report)

        on_progress(98.0, "finalizing")
        return {
            "status": "succeeded",
            "recap_file": recap_path.name,
            "report_file": report_path.name,
            "clip_count": len(specs),
            "ost0_count": sum(1 for s in specs if s.ost == 0),
            "ost1_count": sum(1 for s in specs if s.ost == 1),
            "timeline_duration_sec": report["timeline_duration_sec"],
            "backend": backend,
            "narration_language": language,
            "size_bytes": recap_path.stat().st_size,
        }

    @staticmethod
    def _run_ffmpeg(command: list[str], log_path: Path, should_cancel) -> None:
        try:
            run_stage_command(command, log_path=log_path, should_cancel=should_cancel)
        except StageSubprocessError as exc:
            raise RuntimeError(describe_ffmpeg_failure(exc)) from exc

    @staticmethod
    def _build_report(specs, narration_durations, meta, backend, language) -> dict[str, Any]:
        timeline = round(sum(spec.av_duration for spec in specs), 3)
        return {
            "backend": backend,
            "narration_language": language,
            "commentary_style": meta.get("commentary_style"),
            "timeline_duration_sec": timeline,
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


register_tool(
    ToolSpec(
        tool_id="commentary-render",
        name_zh="解说渲染",
        name_en="Commentary Render",
        description_zh="将解说文案 commentary.json 与源视频合成为成片解说视频：OST=0 配音盖在压低的原声上、OST=1 保留原声，逐段裁剪后拼接（输出 recap.mp4）",
        description_en="Assemble a commentary.json script + source video into a finished recap MP4: OST=0 narration over ducked original, OST=1 original passthrough, cut per item then concatenated",
        category="video",
        icon="Clapperboard",
        accept_formats=[".json", ".mp4", ".mkv", ".mov", ".avi", ".webm", ".wav", ".mp3", ".flac", ".m4a"],
        max_file_size_mb=4096,
        max_files=3,
        heavy=True,
    ),
    CommentaryRenderAdapter,
)
