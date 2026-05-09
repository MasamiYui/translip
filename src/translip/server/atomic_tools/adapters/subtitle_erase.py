from __future__ import annotations

import json
import platform
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ....orchestration.subprocess_runner import run_stage_command
from ..registry import ToolSpec, register_tool
from ..schemas import SubtitleErasePreset, SubtitleEraseToolRequest
from . import ProgressCallback, ToolAdapter


_TQDM_PERCENT_RE = re.compile(r"(\d{1,3})%\|")
_LOG_STAGE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"detecting subtitles", re.IGNORECASE), "detecting_subtitles"),
    (re.compile(r"reading detection", re.IGNORECASE), "reading_detection"),
    (re.compile(r"building masks", re.IGNORECASE), "building_masks"),
    (re.compile(r"loading LaMa", re.IGNORECASE), "loading_lama"),
    (re.compile(r"downloading LaMa", re.IGNORECASE), "downloading_lama"),
    (re.compile(r"auto[- ]tune", re.IGNORECASE), "auto_tuning"),
)


def _build_progress_line_handler(
    *,
    on_progress: ProgressCallback,
    start_percent: float,
    end_percent: float,
    initial_step: str,
) -> Callable[[str], None]:
    state = {"step": initial_step, "last_percent": -1.0}

    def _emit(percent: float, step: str) -> None:
        clamped = max(start_percent, min(end_percent, percent))
        if clamped <= state["last_percent"] and step == state["step"]:
            return
        state["last_percent"] = clamped
        state["step"] = step
        on_progress(clamped, step)

    def _handle(line: str) -> None:
        match = _TQDM_PERCENT_RE.search(line)
        if match:
            ratio = max(0.0, min(100.0, float(match.group(1)))) / 100.0
            mapped = start_percent + (end_percent - start_percent) * ratio
            _emit(mapped, state["step"])
            return
        for pattern, stage in _LOG_STAGE_PATTERNS:
            if pattern.search(line):
                _emit(state["last_percent"] if state["last_percent"] >= 0 else start_percent, stage)
                return

    return _handle


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[5]


def _resolve_erase_project_root() -> Path:
    return (_repo_root().parent / "video-subtitle-erasure").resolve()


def _resolve_ocr_project_root() -> Path:
    return (_repo_root().parent / "subtitle-ocr").resolve()


def _resolve_erase_python() -> Path:
    erase_project_root = _resolve_erase_project_root()
    venv_python = erase_project_root / ".venv" / "bin" / "python"
    if venv_python.exists():
        return venv_python
    ocr_venv_python = _resolve_ocr_project_root() / ".venv" / "bin" / "python"
    if ocr_venv_python.exists():
        return ocr_venv_python
    return Path(sys.executable).resolve()


def _default_lama_device() -> str:
    if platform.system() == "Darwin":
        return "mps"
    return "auto"


@dataclass(frozen=True, slots=True)
class PresetProfile:
    backend: str
    mask_dilate_x: int
    mask_dilate_y: int
    mask_temporal_radius: int
    context_frames: int
    event_lead_frames: int
    event_trail_frames: int
    cleanup_max_coverage: float
    temporal_consensus: int
    temporal_std_threshold: float
    inpaint_radius: int
    inpaint_context_margin: int
    lama_device: str


PRESETS: dict[SubtitleErasePreset, PresetProfile] = {
    "fast": PresetProfile(
        backend="telea",
        mask_dilate_x=16,
        mask_dilate_y=12,
        mask_temporal_radius=2,
        context_frames=14,
        event_lead_frames=3,
        event_trail_frames=8,
        cleanup_max_coverage=0.12,
        temporal_consensus=2,
        temporal_std_threshold=14.0,
        inpaint_radius=5,
        inpaint_context_margin=100,
        lama_device="cpu",
    ),
    "balanced": PresetProfile(
        backend="flow-guided",
        mask_dilate_x=18,
        mask_dilate_y=14,
        mask_temporal_radius=2,
        context_frames=16,
        event_lead_frames=3,
        event_trail_frames=10,
        cleanup_max_coverage=0.12,
        temporal_consensus=2,
        temporal_std_threshold=14.0,
        inpaint_radius=5,
        inpaint_context_margin=120,
        lama_device="cpu",
    ),
    "quality": PresetProfile(
        backend="lama",
        mask_dilate_x=18,
        mask_dilate_y=14,
        mask_temporal_radius=2,
        context_frames=16,
        event_lead_frames=3,
        event_trail_frames=10,
        cleanup_max_coverage=0.10,
        temporal_consensus=2,
        temporal_std_threshold=12.0,
        inpaint_radius=5,
        inpaint_context_margin=140,
        lama_device=_default_lama_device(),
    ),
}


def resolve_preset_params(params: dict[str, Any]) -> dict[str, Any]:
    preset_name: SubtitleErasePreset = params.get("preset", "fast")
    base = PRESETS[preset_name]
    merged = {
        "backend": params.get("backend") or base.backend,
        "mode": params.get("mode", "auto"),
        "regions": params.get("regions") or None,
        "mask_dilate_x": params.get("mask_dilate_x") if params.get("mask_dilate_x") is not None else base.mask_dilate_x,
        "mask_dilate_y": params.get("mask_dilate_y") if params.get("mask_dilate_y") is not None else base.mask_dilate_y,
        "mask_temporal_radius": params.get("mask_temporal_radius") if params.get("mask_temporal_radius") is not None else base.mask_temporal_radius,
        "context_frames": base.context_frames,
        "event_lead_frames": params.get("event_lead_frames") if params.get("event_lead_frames") is not None else base.event_lead_frames,
        "event_trail_frames": params.get("event_trail_frames") if params.get("event_trail_frames") is not None else base.event_trail_frames,
        "cleanup_max_coverage": params.get("cleanup_max_coverage") if params.get("cleanup_max_coverage") is not None else base.cleanup_max_coverage,
        "temporal_consensus": params.get("temporal_consensus") if params.get("temporal_consensus") is not None else base.temporal_consensus,
        "temporal_std_threshold": params.get("temporal_std_threshold") if params.get("temporal_std_threshold") is not None else base.temporal_std_threshold,
        "inpaint_radius": base.inpaint_radius,
        "inpaint_context_margin": base.inpaint_context_margin,
        "lama_device": base.lama_device,
        "auto_tune": bool(params.get("auto_tune", False)),
    }
    return merged


def build_eraser_command(
    *,
    input_video: Path,
    output_video: Path,
    detection_json: Path,
    debug_dir: Path,
    resolved: dict[str, Any],
) -> list[str]:
    cmd: list[str] = [
        str(_resolve_erase_python()),
        "-m",
        "subtitle_eraser.cli",
        "--input",
        str(input_video),
        "--output",
        str(output_video),
        "--subtitle-ocr-project",
        str(_resolve_ocr_project_root()),
        "--reuse-detection",
        str(detection_json),
        "--debug-dir",
        str(debug_dir),
        "--inpaint-backend",
        str(resolved["backend"]),
        "--mode",
        str(resolved["mode"]),
        "--mask-dilate-x",
        str(int(resolved["mask_dilate_x"])),
        "--mask-dilate-y",
        str(int(resolved["mask_dilate_y"])),
        "--mask-temporal-radius",
        str(int(resolved["mask_temporal_radius"])),
        "--context-frames",
        str(int(resolved["context_frames"])),
        "--event-lead-frames",
        str(int(resolved["event_lead_frames"])),
        "--event-trail-frames",
        str(int(resolved["event_trail_frames"])),
        "--cleanup-max-coverage",
        f"{float(resolved['cleanup_max_coverage']):.4f}",
        "--temporal-consensus",
        str(int(resolved["temporal_consensus"])),
        "--temporal-std-threshold",
        f"{float(resolved['temporal_std_threshold']):.4f}",
        "--inpaint-radius",
        str(int(resolved["inpaint_radius"])),
        "--inpaint-context-margin",
        str(int(resolved["inpaint_context_margin"])),
        "--lama-device",
        str(resolved["lama_device"]),
    ]
    if resolved.get("regions"):
        for region in resolved["regions"]:
            x1, y1, x2, y2 = region
            cmd.extend([
                "--region",
                f"{float(x1):.4f},{float(y1):.4f},{float(x2):.4f},{float(y2):.4f}",
            ])
    if resolved.get("auto_tune"):
        cmd.append("--auto-tune")
    return cmd


def build_eraser_env() -> dict[str, str]:
    erase_project_root = _resolve_erase_project_root()
    existing = [entry for entry in sys.path if entry]
    pythonpath = ":".join([str(erase_project_root), *existing])
    return {"PYTHONPATH": pythonpath}


class SubtitleEraseAdapter(ToolAdapter):
    def validate_params(self, params: dict) -> dict:
        return SubtitleEraseToolRequest(**params).model_dump()

    def run(self, params, input_dir, output_dir, on_progress):
        input_file = self.first_input(input_dir, "file")
        detection_file, detection_source = self._resolve_detection(
            params=params,
            input_dir=input_dir,
            output_dir=output_dir,
            original_video=input_file,
            on_progress=on_progress,
        )
        on_progress(20.0, "preparing")

        resolved = resolve_preset_params(params)

        erased_path = output_dir / "erased.mp4"
        debug_dir = output_dir / "debug"
        log_path = output_dir / "erase.log"

        cmd = build_eraser_command(
            input_video=input_file,
            output_video=erased_path,
            detection_json=detection_file,
            debug_dir=debug_dir,
            resolved=resolved,
        )
        env = build_eraser_env()

        on_progress(25.0, f"erasing_{resolved['backend']}")
        progress_handler = _build_progress_line_handler(
            on_progress=on_progress,
            start_percent=25.0,
            end_percent=88.0,
            initial_step=f"erasing_{resolved['backend']}",
        )
        run_stage_command(
            cmd,
            log_path=log_path,
            env_overrides=env,
            on_stdout_line=progress_handler,
            should_cancel=getattr(on_progress, "is_cancelled", None),
        )

        if not erased_path.exists():
            raise RuntimeError("Subtitle erasure did not produce an output video")

        on_progress(90.0, "evaluating")
        metrics = _quick_metrics(input_file, erased_path, detection_file)

        report = {
            "preset": params.get("preset", "fast"),
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
            "preset": params.get("preset", "fast"),
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
            {"file_id": "__auto__"}
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
                "Auto detection did not produce detection.json; "
                "please upload a detection file explicitly."
            )
        return detection_path, "auto"


def _quick_metrics(
    original_video: Path,
    erased_video: Path,
    detection_json: Path,
    sample_frames: int = 30,
) -> dict[str, Any]:
    try:
        import cv2  # type: ignore
        import numpy as np  # type: ignore
    except ImportError:
        return {"error": "cv2_or_numpy_not_available"}

    try:
        detection = json.loads(detection_json.read_text(encoding="utf-8"))
    except Exception:
        detection = {}
    events = detection.get("events") or detection.get("results") or []

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
        description_zh="擦除视频中的硬字幕（支持 fast/balanced/quality 三档预设）",
        description_en="Remove hardcoded subtitles from video (fast/balanced/quality presets)",
        category="video",
        icon="Eraser",
        accept_formats=[".mp4", ".mkv", ".avi", ".mov", ".json"],
        max_file_size_mb=2048,
        max_files=2,
    ),
    SubtitleEraseAdapter,
)
