"""Separation scenario: run (demucs/cdx23) → SI-SDR vs known clean stems.

Quantitative only against synthetic mixes or user-provided real stems (folder
dataset ``<stem>.voice.wav`` + ``<stem>.background.wav``).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..core.invoke import Invoker, StageResult
from ..core.media import load_audio
from ..core.sample import Sample
from ..core.scenario import Scenario, register_scenario
from ..metrics.audio import sdr, si_sdr


class SeparationScenario(Scenario):
    name = "separation"
    primary_metric_key = "si_sdr"
    higher_is_better = True

    def required_gt(self) -> list[str]:
        return ["clean_stems"]

    def input_paths(self, sample: Sample) -> list[str | Path]:
        return [sample.media_path, *sample.ground_truth.clean_stems.values()]

    def invoke(self, sample, work_dir, invoker, *, config, timeout, log_path) -> StageResult:
        out_dir = work_dir / "separation"
        args = ["--input", str(sample.media_path), "--output-dir", str(out_dir),
                "--mode", str(config.get("mode", "auto"))]
        for flag, key in (("--quality", "quality"), ("--device", "device")):
            if config.get(key):
                args += [flag, str(config[key])]
        return invoker.translip("run", args, timeout=timeout, log_path=log_path)

    def score(self, sample, work_dir, stage, config) -> dict[str, Any]:
        voice_out = (stage.outputs or {}).get("voice") if stage else None
        if not voice_out or not Path(voice_out).is_file():
            raise RuntimeError("separation did not emit a readable voice track")
        gt_voice = sample.ground_truth.clean_stems.get("voice")
        if not gt_voice:
            raise RuntimeError("clean_stems missing 'voice' reference")
        ref, sr = load_audio(gt_voice)
        est, _ = load_audio(voice_out, target_sr=sr)
        metrics = {"si_sdr": si_sdr(est, ref), "sdr": sdr(est, ref)}
        bg_out = (stage.outputs or {}).get("background")
        gt_bg = sample.ground_truth.clean_stems.get("background")
        if bg_out and Path(bg_out).is_file() and gt_bg:
            ref_bg, sr_bg = load_audio(gt_bg)
            est_bg, _ = load_audio(bg_out, target_sr=sr_bg)
            metrics["si_sdr_background"] = si_sdr(est_bg, ref_bg)
        return metrics


register_scenario(SeparationScenario())
