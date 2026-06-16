"""OCR-detect scenario: translip.ocr.extract → subtitle recognition vs GT.

Two time-aware metrics (sampled timestamps; at each, GT-active events are matched
against detection-active events):

- **text_f1** (primary) — match by normalized text equality. This measures "right
  subtitle text at the right time", which is what the subtitle pipeline needs and
  is robust to detector box conventions.
- **box_f1** (secondary) — match by IoU at ``iou`` threshold. Detectors return
  looser/taller boxes than tight glyph GT, so box IoU is the stricter, less
  forgiving view.

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
        start = e.get("start", e.get("start_time", 0.0))
        end = e.get("end", e.get("end_time", start))
        out.append({
            "start": float(start), "end": float(end),
            "box": [float(v) for v in box] if box and len(box) == 4 else None,
            "text": e.get("text", ""),
        })
    return out


def _norm_text(text: str) -> str:
    return "".join(str(text).split())  # drop whitespace; CJK has no word spacing


def _text_match_counts(pred_texts: list[str], gt_texts: list[str]) -> tuple[int, int, int]:
    used = [False] * len(gt_texts)
    tp = 0
    for pt in pred_texts:
        if not pt:
            continue
        for i, gt in enumerate(gt_texts):
            if not used[i] and gt and pt == gt:
                used[i] = True
                tp += 1
                break
    return tp, len(pred_texts) - tp, len(gt_texts) - tp


class OcrDetectScenario(Scenario):
    name = "ocr-detect"
    primary_metric_key = "text_f1"
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
        step = float(config.get("eval_step", 0.5))

        end_time = max([e["end"] for e in gt] + [e["end"] for e in pred] + [1.0])
        box_tp = box_fp = box_fn = 0
        txt_tp = txt_fp = txt_fn = 0
        t = step / 2
        while t < end_time:
            gt_a = [e for e in gt if e["start"] <= t < e["end"]]
            pr_a = [e for e in pred if e["start"] <= t <= e["end"]]
            box_m = match_boxes([e["box"] for e in pr_a if e["box"]],
                                [e["box"] for e in gt_a if e["box"]], iou_threshold=iou)
            box_tp += box_m["tp"]
            box_fp += box_m["fp"]
            box_fn += box_m["fn"]
            tp, fp, fn = _text_match_counts([_norm_text(e["text"]) for e in pr_a],
                                            [_norm_text(e["text"]) for e in gt_a])
            txt_tp += tp
            txt_fp += fp
            txt_fn += fn
            t += step

        text = prf(txt_tp, txt_fp, txt_fn)
        box = prf(box_tp, box_fp, box_fn)
        return {
            "text_f1": text["f1"], "text_precision": text["precision"], "text_recall": text["recall"],
            "text_tp": txt_tp, "text_fp": txt_fp, "text_fn": txt_fn,
            "box_f1": box["f1"], "box_precision": box["precision"], "box_recall": box["recall"],
            "tp": box_tp, "fp": box_fp, "fn": box_fn,
            "gt_event_count": len(gt), "pred_event_count": len(pred), "iou_threshold": iou,
        }

    def corpus_metrics(self, metrics_list):
        out: dict[str, Any] = {}
        ttp = sum(m.get("text_tp", 0) for m in metrics_list)
        tfp = sum(m.get("text_fp", 0) for m in metrics_list)
        tfn = sum(m.get("text_fn", 0) for m in metrics_list)
        if (ttp + tfp + tfn) > 0:
            s = prf(ttp, tfp, tfn)
            out.update({"text_f1_micro": round(s["f1"], 4), "text_precision_micro": round(s["precision"], 4),
                        "text_recall_micro": round(s["recall"], 4)})
        btp = sum(m.get("tp", 0) for m in metrics_list)
        bfp = sum(m.get("fp", 0) for m in metrics_list)
        bfn = sum(m.get("fn", 0) for m in metrics_list)
        if (btp + bfp + bfn) > 0:
            s = prf(btp, bfp, bfn)
            out["box_f1_micro"] = round(s["f1"], 4)
        return out


register_scenario(OcrDetectScenario())
