"""Subtitle-erase scenario: ocr.extract → erase.extract → PSNR/SSIM vs clean GT.

Erasure quality = how close the cleaned video is to the subtitle-free reference,
measured on frames sampled *during* subtitle windows (where inpainting happened).
Requires the ``ocr`` + ``erase`` extras; absent → the stage errors and the result
is marked failed.
"""
from __future__ import annotations

import json
from pathlib import Path
from statistics import mean
from typing import Any

from ..core.invoke import Invoker, StageResult
from ..core.media import extract_frame, probe_video
from ..core.sample import Sample
from ..core.scenario import Scenario, register_scenario
from ..metrics.image import psnr, ssim

_PSNR_CAP = 100.0  # finite stand-in for identical frames so means stay numeric


class SubtitleEraseScenario(Scenario):
    name = "subtitle-erase"
    primary_metric_key = "ssim"
    higher_is_better = True

    def required_gt(self) -> list[str]:
        return ["clean_video"]

    def input_paths(self, sample: Sample) -> list[str | Path]:
        return [sample.media_path, sample.ground_truth.clean_video]

    def invoke(self, sample, work_dir, invoker, *, config, timeout, log_path) -> StageResult:
        ocr_dir = work_dir / "ocr"
        ocr_dir.mkdir(parents=True, exist_ok=True)
        r1 = invoker.module(
            "translip.ocr.extract",
            ["--input", str(sample.media_path), "--output-dir", str(ocr_dir),
             "--language", config.get("ocr_language", "ch")],
            timeout=timeout, log_path=work_dir / "ocr.log",
        )
        if not r1.ok:
            return r1
        erase_dir = work_dir / "erase"
        args = ["--input", str(sample.media_path), "--output-dir", str(erase_dir),
                "--detection", str(ocr_dir / "detection.json"),
                "--backend", str(config.get("erase_backend", "sttn"))]
        if config.get("device"):
            args += ["--device", str(config["device"])]
        return invoker.module("translip.erase.extract", args, timeout=timeout, log_path=log_path)

    def _sample_times(self, sample: Sample, max_t: float) -> list[float]:
        times: list[float] = []
        boxes = sample.ground_truth.subtitle_boxes
        if boxes and Path(boxes).is_file():
            data = json.loads(Path(boxes).read_text(encoding="utf-8"))
            for e in data.get("events", []):
                start = e.get("start", e.get("start_time"))
                end = e.get("end", e.get("end_time"))
                if start is not None and end is not None:
                    times.append((float(start) + float(end)) / 2)
        if not times:
            t = 0.5
            while t < max_t:
                times.append(t)
                t += 1.0
        return [t for t in times if 0 <= t < max_t] or [min(0.5, max(0.0, max_t - 0.1))]

    def score(self, sample, work_dir, stage, config) -> dict[str, Any]:
        erased = work_dir / "erase" / "clean_video.mp4"
        if not erased.is_file():
            raise RuntimeError(f"erase produced no clean_video.mp4 at {erased}")
        gt_clean = Path(sample.ground_truth.clean_video)
        max_t = min(probe_video(erased).duration_sec, probe_video(gt_clean).duration_sec) - 0.05
        times = self._sample_times(sample, max_t)

        psnrs: list[float] = []
        ssims: list[float] = []
        for t in times:
            a = extract_frame(erased, t)
            b = extract_frame(gt_clean, t)
            p = psnr(a, b)
            psnrs.append(_PSNR_CAP if p == float("inf") else p)
            ssims.append(ssim(a, b))
        return {"psnr": round(mean(psnrs), 3), "ssim": round(mean(ssims), 4), "frames": len(times)}


register_scenario(SubtitleEraseScenario())
