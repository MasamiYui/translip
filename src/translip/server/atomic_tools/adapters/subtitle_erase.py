from __future__ import annotations

import json
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ....orchestration.erase_bridge import parse_erase_progress_line
from ....orchestration.subprocess_runner import run_stage_command
from ....orchestration.subtitle_erase_detection import prepare_subtitle_erase_detection
from ..registry import ToolSpec, register_tool
from ..schemas import SubtitleErasePreset, SubtitleEraseToolRequest
from . import ProgressCallback, ToolAdapter


@dataclass(frozen=True, slots=True)
class PresetProfile:
    backend: str
    mask_dilate_x: int
    mask_dilate_y: int
    max_load: int


PRESETS: dict[SubtitleErasePreset, PresetProfile] = {
    # balanced: STTN video inpainting — temporal coherence, best general default.
    "balanced": PresetProfile(backend="sttn", mask_dilate_x=12, mask_dilate_y=8, max_load=50),
    # quality: big-LaMa single-frame — sharpest fills (animation/stills); heavier.
    "quality": PresetProfile(backend="lama", mask_dilate_x=12, mask_dilate_y=8, max_load=30),
}


def resolve_preset_params(params: dict[str, Any]) -> dict[str, Any]:
    preset_name: SubtitleErasePreset = params.get("preset", "balanced")
    base = PRESETS[preset_name]

    def pick(key: str, default: Any) -> Any:
        value = params.get(key)
        return value if value is not None else default

    return {
        "backend": params.get("backend") or base.backend,
        "device": params.get("device") or "auto",
        "mask_dilate_x": pick("mask_dilate_x", base.mask_dilate_x),
        "mask_dilate_y": pick("mask_dilate_y", base.mask_dilate_y),
        "max_load": pick("max_load", base.max_load),
        "event_lead_frames": pick("event_lead_frames", 3),
        "event_trail_frames": pick("event_trail_frames", 8),
        "regions": params.get("regions") or None,
    }


def build_eraser_command(
    *,
    input_video: Path,
    output_dir: Path,
    output_name: str,
    detection_json: Path | None,
    resolved: dict[str, Any],
) -> list[str]:
    cmd: list[str] = [
        sys.executable,
        "-m",
        "translip.erase.extract",
        "--input",
        str(input_video),
        "--output-dir",
        str(output_dir),
        "--output-name",
        output_name,
        "--backend",
        str(resolved["backend"]),
        "--device",
        str(resolved["device"]),
        "--mask-dilate-x",
        str(int(resolved["mask_dilate_x"])),
        "--mask-dilate-y",
        str(int(resolved["mask_dilate_y"])),
        "--max-load",
        str(int(resolved["max_load"])),
    ]
    if detection_json is not None:
        cmd.extend(["--detection", str(detection_json)])
    if resolved.get("regions"):
        for x1, y1, x2, y2 in resolved["regions"]:
            cmd.extend(["--region", f"{float(x1):.4f},{float(y1):.4f},{float(x2):.4f},{float(y2):.4f}"])
    return cmd


def _build_progress_handler(
    *, on_progress: ProgressCallback, start_percent: float, end_percent: float
) -> Callable[[str], None]:
    def _handle(line: str) -> None:
        parsed = parse_erase_progress_line(line)
        if parsed is None:
            return
        ratio = max(0.0, min(100.0, parsed[0])) / 100.0
        on_progress(start_percent + (end_percent - start_percent) * ratio, parsed[1])

    return _handle


class SubtitleEraseAdapter(ToolAdapter):
    def validate_params(self, params: dict) -> dict:
        return SubtitleEraseToolRequest(**params).model_dump()

    def run(self, params, input_dir, output_dir, on_progress):
        input_file = self.first_input(input_dir, "file")
        resolved = resolve_preset_params(params)

        # Manual region mode skips detection entirely; otherwise resolve (or
        # auto-detect) an OCR detection.json and expand it for fade in/out.
        detection_file: Path | None = None
        detection_source = "regions"
        if not resolved.get("regions"):
            raw_detection, detection_source = self._resolve_detection(
                params=params,
                input_dir=input_dir,
                output_dir=output_dir,
                original_video=input_file,
                on_progress=on_progress,
            )
            detection_file = prepare_subtitle_erase_detection(
                raw_detection,
                output_dir / "reuse_detection.expanded.json",
                lead_frames=int(resolved["event_lead_frames"]),
                trail_frames=int(resolved["event_trail_frames"]),
                video_path=input_file,
            )
        on_progress(20.0, "preparing")

        erased_path = output_dir / "erased.mp4"
        log_path = output_dir / "erase.log"
        cmd = build_eraser_command(
            input_video=input_file,
            output_dir=output_dir,
            output_name=erased_path.name,
            detection_json=detection_file,
            resolved=resolved,
        )

        on_progress(22.0, f"erasing_{resolved['backend']}")
        run_stage_command(
            cmd,
            log_path=log_path,
            on_stdout_line=_build_progress_handler(on_progress=on_progress, start_percent=22.0, end_percent=96.0),
            should_cancel=getattr(on_progress, "is_cancelled", None),
        )

        if not erased_path.exists():
            raise RuntimeError("Subtitle erasure did not produce an output video")

        on_progress(97.0, "evaluating")
        metrics = _quick_metrics(input_file, erased_path, detection_file)

        report = {
            "preset": params.get("preset", "balanced"),
            "resolved_parameters": resolved,
            "metrics": metrics,
            "detection_source": detection_source,
        }
        report_path = output_dir / "report.json"
        self.write_json(report_path, report)

        on_progress(98.0, "collecting_artifacts")
        return {
            "erased_file": erased_path.name,
            "report_file": report_path.name,
            "preset": params.get("preset", "balanced"),
            "backend": resolved["backend"],
            "metrics": metrics,
            "detection_source": detection_source,
        }

    def _resolve_detection(
        self,
        *,
        params: dict,
        input_dir: Path,
        output_dir: Path,
        original_video: Path,
        on_progress: ProgressCallback,
    ) -> tuple[Path, str]:
        try:
            detection_file = self.first_input(input_dir, "detection_file")
            return detection_file, "uploaded"
        except StopIteration:
            pass

        on_progress(6.0, "auto_detecting")
        from .subtitle_detect import SubtitleDetectAdapter

        auto_dir = output_dir / "auto_detect"
        auto_input_dir = auto_dir / "input"
        auto_output_dir = auto_dir / "output"
        (auto_input_dir / "file").mkdir(parents=True, exist_ok=True)
        auto_output_dir.mkdir(parents=True, exist_ok=True)

        from shutil import copy2

        copy2(original_video, auto_input_dir / "file" / original_video.name)

        detect_adapter = SubtitleDetectAdapter()
        detect_params = detect_adapter.validate_params(
            {
                "file_id": "__auto__",
                "sample_interval": params.get("sample_interval") or 0.25,
            }
        )
        detect_adapter.run(
            params=detect_params,
            input_dir=auto_input_dir,
            output_dir=auto_output_dir,
            on_progress=lambda pct, stage=None: on_progress(
                6.0 + max(0.0, min(1.0, pct / 100.0)) * 12.0,
                f"auto_detect_{stage}" if stage else "auto_detecting",
            ),
        )

        detection_path = auto_output_dir / "detection.json"
        if not detection_path.exists():
            raise RuntimeError(
                "Auto detection did not produce detection.json; please upload a detection file explicitly."
            )
        return detection_path, "auto"


def _quick_metrics(
    original_video: Path,
    erased_video: Path,
    detection_json: Path | None,
    sample_frames: int = 30,
) -> dict[str, Any]:
    try:
        import cv2  # type: ignore
        import numpy as np  # type: ignore
    except ImportError:
        return {"error": "cv2_or_numpy_not_available"}

    events: list[dict] = []
    if detection_json is not None:
        try:
            detection = json.loads(detection_json.read_text(encoding="utf-8"))
            events = detection.get("events") or detection.get("results") or []
        except Exception:
            events = []

    cap_o = cv2.VideoCapture(str(original_video))
    cap_e = cv2.VideoCapture(str(erased_video))
    try:
        if not cap_o.isOpened() or not cap_e.isOpened():
            return {"error": "failed_to_open_videos"}

        total = int(cap_o.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        total_e = int(cap_e.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        if total == 0 or total_e == 0:
            return {"error": "empty_video"}

        height = int(cap_o.get(cv2.CAP_PROP_FRAME_HEIGHT))
        width = int(cap_o.get(cv2.CAP_PROP_FRAME_WIDTH))

        band_y1, band_y2 = _infer_subtitle_band(events, height)

        indices = np.linspace(0, min(total, total_e) - 1, num=min(sample_frames, total, total_e)).astype(int)

        band_diffs: list[float] = []
        spills: list[float] = []
        for idx in indices:
            cap_o.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
            cap_e.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
            ok_o, frame_o = cap_o.read()
            ok_e, frame_e = cap_e.read()
            if not (ok_o and ok_e):
                continue
            diff = cv2.absdiff(frame_o, frame_e).astype(np.float32)
            band_mask = np.zeros(diff.shape[:2], dtype=bool)
            band_mask[band_y1:band_y2] = True
            band_diffs.append(float(diff[band_mask].mean()))
            outside = diff[~band_mask]
            if outside.size:
                spills.append(float(outside.mean()))

        return {
            "sampled_frames": int(len(indices)),
            "band_diff_mean": round(float(np.mean(band_diffs)), 4) if band_diffs else 0.0,
            "spill_mean": round(float(np.mean(spills)), 4) if spills else 0.0,
            "subtitle_band": {"y1": band_y1, "y2": band_y2, "height": height},
        }
    finally:
        cap_o.release()
        cap_e.release()


def _infer_subtitle_band(events: list[dict], height: int) -> tuple[int, int]:
    if events:
        y1s: list[int] = []
        y2s: list[int] = []
        for ev in events:
            box = ev.get("box") or ev.get("bbox") or ev.get("region_box")
            if box and len(box) == 4:
                y1s.append(int(box[1]))
                y2s.append(int(box[3]))
        if y1s and y2s:
            return max(0, min(y1s) - 6), min(height, max(y2s) + 6)
    return int(height * 0.78), int(height * 0.97)


register_tool(
    ToolSpec(
        tool_id="subtitle-erase",
        name_zh="字幕擦除",
        name_en="Subtitle Erase",
        description_zh="擦除视频中的硬字幕（balanced=STTN / quality=LaMa 两档预设）",
        description_en="Remove hardcoded subtitles from video (balanced=STTN / quality=LaMa presets)",
        category="video",
        icon="Eraser",
        accept_formats=[".mp4", ".mkv", ".avi", ".mov", ".json"],
        max_file_size_mb=2048,
        max_files=2,
    ),
    SubtitleEraseAdapter,
)
