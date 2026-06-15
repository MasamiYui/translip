"""OCR-detect scenario: translip.ocr.extract → box detection F1 vs subtitle GT.

Evaluation is time-aware: at sampled timestamps, the active GT boxes are matched
(by IoU) against the active detected boxes, accumulating tp/fp/fn. This separates
events that share the same on-screen region but appear at different times.
Requires the ``ocr`` extra (PaddleOCR); absent → the stage errors and the result
is marked failed.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..core.invoke import Invoker, StageResult
from ..core.sample import Sample
from ..core.scenario import Scenario, register_scenario
from ..metrics.detection import match_boxes, prf


def _events(payload: dict) -> list[dict]:
    out = []
    for e in payload.get("events", []):
        box = e.get("box")
        if not box or len(box) != 4:
            continue
        start = e.get("start", e.get("start_time", 0.0))
        end = e.get("end", e.get("end_time", start))
        out.append({"start": float(start), "end": float(end), "box": [float(v) for v in box],
                    "text": e.get("text", "")})
    return out


class OcrDetectScenario(Scenario):
    name = "ocr-detect"
    primary_metric_key = "f1"
    higher_is_better = True

    def required_gt(self) -> list[str]:
        return ["subtitle_boxes"]

    def input_paths(self, sample: Sample) -> list[str | Path]:
        return [sample.media_path, sample.ground_truth.subtitle_boxes]

    def invoke(self, sample, work_dir, invoker, *, config, timeout, log_path) -> StageResult:
        out_dir = work_dir / "ocr-detect"
        out_dir.mkdir(parents=True, exist_ok=True)
        lang = config.get("ocr_language", "ch")
        args = ["--input", str(sample.media_path), "--output-dir", str(out_dir), "--language", lang]
        for flag, key in (("--sample-interval", "sample_interval"),
                          ("--position-mode", "position_mode"),
                          ("--extraction-mode", "extraction_mode")):
            if config.get(key) is not None:
                args += [flag, str(config[key])]
        return invoker.module("translip.ocr.extract", args, timeout=timeout, log_path=log_path)

    def score(self, sample, work_dir, stage, config) -> dict[str, Any]:
        det_path = work_dir / "ocr-detect" / "detection.json"
        if not det_path.is_file():
            raise RuntimeError(f"OCR produced no detection.json at {det_path}")
        pred = _events(json.loads(det_path.read_text(encoding="utf-8")))
        gt = _events(json.loads(Path(sample.ground_truth.subtitle_boxes).read_text(encoding="utf-8")))
        iou = float(config.get("iou", 0.5))

        end_time = max([e["end"] for e in gt] + [e["end"] for e in pred] + [1.0])
        step = float(config.get("eval_step", 0.5))
        tp = fp = fn = 0
        t = step / 2
        while t < end_time:
            gt_boxes = [e["box"] for e in gt if e["start"] <= t < e["end"]]
            pred_boxes = [e["box"] for e in pred if e["start"] <= t <= e["end"]]
            m = match_boxes(pred_boxes, gt_boxes, iou_threshold=iou)
            tp += m["tp"]
            fp += m["fp"]
            fn += m["fn"]
            t += step
        scores = prf(tp, fp, fn)
        scores.update({"gt_event_count": len(gt), "pred_event_count": len(pred), "iou_threshold": iou})
        return scores


register_scenario(OcrDetectScenario())
