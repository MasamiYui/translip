"""End-to-end dubbing scenario: run-pipeline → benchmark-dub honest score.

Intrinsic (no external GT): reuses translip's own dub benchmark "honest score"
(0–100) as the primary metric, so a real Chinese clip can be run through the whole
pipeline and scored for regression. Use MER2024 / TMCSpeech clips as inputs.
Heavy: needs the separation/ASR/TTS stacks (and possibly DEEPSEEK_API_KEY for the
deepseek translation backend).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..core.invoke import Invoker, StageResult
from ..core.sample import Sample
from ..core.scenario import Scenario, register_scenario


class E2EDubScenario(Scenario):
    name = "e2e-dub"
    primary_metric_key = "score"
    higher_is_better = True

    def required_gt(self) -> list[str]:
        return []  # intrinsic quality, no external ground truth

    def invoke(self, sample, work_dir, invoker, *, config, timeout, log_path) -> StageResult:
        out_root = work_dir / "pipeline"
        args = ["--input", str(sample.media_path), "--output-root", str(out_root),
                "--template", str(config.get("template", "asr-dub-basic"))]
        for flag, key in (("--target-lang", "target_lang"), ("--translation-backend", "translation_backend"),
                          ("--tts-backend", "tts_backend"), ("--device", "device")):
            if config.get(key):
                args += [flag, str(config[key])]
        r1 = invoker.translip("run-pipeline", args, timeout=timeout, log_path=work_dir / "pipeline.log")
        if not r1.ok:
            return r1
        bench = ["--pipeline-root", str(out_root), "--output-dir", str(work_dir / "benchmark"),
                 "--target-lang", str(config.get("target_lang", "en"))]
        return invoker.translip("benchmark-dub", bench, timeout=timeout, log_path=log_path)

    def score(self, sample, work_dir, stage, config) -> dict[str, Any]:
        outputs = (stage.outputs or {}) if stage else {}
        raw = outputs.get("score")
        if raw is None:
            raise RuntimeError("benchmark-dub emitted no score")
        result: dict[str, Any] = {"score": float(raw), "status": outputs.get("status")}
        bench_path = outputs.get("benchmark")
        if bench_path and Path(bench_path).is_file():
            data = json.loads(Path(bench_path).read_text(encoding="utf-8"))
            metrics = data.get("metrics", data)
            for key in ("coverage_ratio", "undubbed_ratio", "overall_failed_ratio"):
                value = metrics.get(key)
                if isinstance(value, (int, float)):
                    result[key] = value
        return result


register_scenario(E2EDubScenario())
