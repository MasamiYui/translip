from __future__ import annotations

import json
import sys
from pathlib import Path

from ....orchestration.subprocess_runner import run_stage_command
from ..cancellation import cancel_checker
from ..registry import ToolSpec, register_tool
from ..schemas import VideoAnalyzeToolRequest
from . import ToolAdapter

# Must match translip.vision.extract.PROGRESS_PREFIX (kept as a literal so this
# adapter stays free of the vision stack at import time).
_VISION_PROGRESS_PREFIX = "__VISION_PROGRESS__"

_RESULT_FILES = {
    "scene-context": "visual_context.json",
    "erase-qc": "erase_qc_report.json",
    "ocr-classify": "ocr_events.classified.json",
    "freeform": "freeform_answer.json",
}


def parse_vision_progress_line(line: str) -> tuple[float, str] | None:
    """Parse one `__VISION_PROGRESS__\\t<pct>\\t<message>` line from the extractor."""
    if not line.startswith(_VISION_PROGRESS_PREFIX + "\t"):
        return None
    parts = line.split("\t", 2)
    if len(parts) < 2:
        return None
    try:
        percent = float(parts[1])
    except ValueError:
        return None
    return percent, parts[2] if len(parts) > 2 else "analyzing video"


class VideoAnalyzeAdapter(ToolAdapter):
    def validate_params(self, params: dict) -> dict:
        return VideoAnalyzeToolRequest(**params).model_dump()

    def run(self, params, input_dir, output_dir, on_progress):
        input_file = self.first_input(input_dir, "file")
        on_progress(2.0, "preparing")

        stage_dir = output_dir
        stage_dir.mkdir(parents=True, exist_ok=True)
        log_path = stage_dir / "video_analyze.log"
        task = params.get("task", "scene-context")

        # In-tree Qwen3-VL analysis, run in an isolated subprocess so the model
        # is freed on exit (matches the ocr/erase adapters).
        cmd = [
            sys.executable,
            "-m",
            "translip.vision.extract",
            "--input",
            str(input_file),
            "--output-dir",
            str(stage_dir),
            "--task",
            task,
            "--sample-interval",
            str(params.get("sample_interval", 10.0)),
            "--frames-per-unit",
            str(params.get("frames_per_unit", 4)),
            "--lang",
            params.get("lang", "zh"),
            "--backend",
            params.get("backend", "auto"),
        ]
        if params.get("question"):
            cmd.extend(["--question", str(params["question"])])
        if params.get("detection_file_id"):
            detection_file = self.first_input(input_dir, "detection_file")
            cmd.extend(["--detection", str(detection_file)])
        if params.get("max_units"):
            cmd.extend(["--max-units", str(int(params["max_units"]))])

        on_progress(5.0, "loading_model")

        def _forward_progress(line: str) -> None:
            parsed = parse_vision_progress_line(line)
            if parsed is None:
                return
            # Map the extractor's 0-100 onto this tool's 5-95 band.
            mapped = 5.0 + (95.0 - 5.0) * max(0.0, min(100.0, parsed[0])) / 100.0
            on_progress(mapped, parsed[1])

        run_stage_command(
            cmd,
            log_path=log_path,
            on_stdout_line=_forward_progress,
            should_cancel=cancel_checker(on_progress),
        )

        manifest_path = stage_dir / f"{task}-manifest.json"
        if not manifest_path.exists():
            raise RuntimeError("video analysis did not produce a manifest")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("status") != "succeeded":
            raise RuntimeError(manifest.get("error") or "video analysis failed")

        result_file = _RESULT_FILES.get(task, "visual_context.json")
        result: dict[str, object] = {
            "task": task,
            "result_file": result_file,
            "manifest_file": manifest_path.name,
            "backend": (manifest.get("model") or {}).get("backend"),
            "model": (manifest.get("model") or {}).get("model"),
            "unit_count": manifest.get("unit_count", 0),
            "error_count": manifest.get("error_count", 0),
        }
        if task == "freeform":
            answer_payload = json.loads((stage_dir / result_file).read_text(encoding="utf-8"))
            result["answer"] = answer_payload.get("answer")
        return result


register_tool(
    ToolSpec(
        tool_id="video-analyze",
        name_zh="视频内容分析",
        name_en="Video Content Analysis",
        description_zh="基于 Qwen3-VL 本地视觉模型分析视频画面：场景描述、画面文字分类、擦除质检、自由问答",
        description_en="Analyze video frames with a local Qwen3-VL model: scene description, on-screen text triage, erase QC, free-form Q&A",
        category="video",
        icon="ScanEye",
        accept_formats=[".mp4", ".mkv", ".avi", ".mov"],
        max_file_size_mb=2048,
        max_files=1,
        heavy=True,
    ),
    VideoAnalyzeAdapter,
)
