"""Diarization scenario: transcribe --enable-diarization → DER vs reference RTTM."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..core.invoke import Invoker, StageResult
from ..core.sample import Sample
from ..core.scenario import Scenario, register_scenario
from ..metrics.diarization import der, parse_rttm


class DiarizationScenario(Scenario):
    name = "diarization"
    primary_metric_key = "der"
    higher_is_better = False

    def required_gt(self) -> list[str]:
        return ["rttm"]

    def input_paths(self, sample: Sample) -> list[str | Path]:
        return [sample.media_path, sample.ground_truth.rttm]

    def invoke(self, sample, work_dir, invoker, *, config, timeout, log_path) -> StageResult:
        out_dir = work_dir / "transcribe"
        lang = config.get("language") or sample.meta.get("lang") or "zh"
        args = ["--input", str(sample.media_path), "--output-dir", str(out_dir),
                "--language", lang, "--enable-diarization"]
        for flag, key in (("--diarizer-backend", "diarizer_backend"), ("--asr-backend", "asr_backend"),
                          ("--asr-model", "asr_model"), ("--device", "device")):
            if config.get(key):
                args += [flag, str(config[key])]
        if config.get("expected_speakers"):
            args += ["--expected-speakers", str(config["expected_speakers"])]
        return invoker.translip("transcribe", args, timeout=timeout, log_path=log_path)

    def score(self, sample, work_dir, stage, config) -> dict[str, Any]:
        seg_path = (stage.outputs or {}).get("segments") if stage else None
        if not seg_path or not Path(seg_path).is_file():
            raise RuntimeError("transcribe did not emit a readable segments JSON")
        payload = json.loads(Path(seg_path).read_text(encoding="utf-8"))
        hyp_segs = [
            (float(s["start"]), float(s["end"]), str(s.get("speaker_label") or "SPK"))
            for s in payload.get("segments", [])
            if s.get("end") is not None and s.get("start") is not None
        ]
        ref_segs = parse_rttm(sample.ground_truth.rttm)
        return der(
            ref_segs, hyp_segs,
            collar=float(config.get("collar", 0.0)),
            ignore_overlap=bool(config.get("ignore_overlap", False)),
        )


register_scenario(DiarizationScenario())
