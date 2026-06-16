"""ASR scenario: transcribe → CER vs reference SRT.

Reuses translip's own ``score_transcription_against_reference`` (the in-tree
benchmark scorer, normalized for Chinese) so lab numbers match translip's
``benchmark-transcription``.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..core.invoke import Invoker, StageResult
from ..core.sample import Sample
from ..core.scenario import Scenario, register_scenario


class AsrScenario(Scenario):
    name = "asr"
    primary_metric_key = "cer"
    higher_is_better = False

    def required_gt(self) -> list[str]:
        return ["transcript_srt"]

    def input_paths(self, sample: Sample) -> list[str | Path]:
        return [sample.media_path, sample.ground_truth.transcript_srt]

    def invoke(self, sample, work_dir, invoker, *, config, timeout, log_path) -> StageResult:
        out_dir = work_dir / "transcribe"
        lang = config.get("language") or sample.meta.get("lang") or "zh"
        args = ["--input", str(sample.media_path), "--output-dir", str(out_dir), "--language", lang]
        for flag, key in (("--asr-backend", "asr_backend"), ("--asr-model", "asr_model"), ("--device", "device")):
            if config.get(key):
                args += [flag, str(config[key])]
        return invoker.translip("transcribe", args, timeout=timeout, log_path=log_path)

    def score(self, sample, work_dir, stage, config) -> dict[str, Any]:
        from translip.transcription.benchmark import parse_srt, score_transcription_against_reference

        seg_path = (stage.outputs or {}).get("segments") if stage else None
        if not seg_path or not Path(seg_path).is_file():
            raise RuntimeError("transcribe did not emit a readable segments JSON")
        hypothesis = json.loads(Path(seg_path).read_text(encoding="utf-8"))
        references = parse_srt(Path(sample.ground_truth.transcript_srt))
        metrics = score_transcription_against_reference(reference_subtitles=references, hypothesis_payload=hypothesis)
        return metrics

    def corpus_metrics(self, metrics_list):
        total_ref = sum((m.get("reference_char_count") or 0) for m in metrics_list)
        if total_ref <= 0:
            return {}
        total_edits = sum((m.get("cer") or 0.0) * (m.get("reference_char_count") or 0) for m in metrics_list)
        return {"cer_micro": round(total_edits / total_ref, 4), "reference_char_total": int(total_ref)}


register_scenario(AsrScenario())
