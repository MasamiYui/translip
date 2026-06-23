"""Voice-clone TTS scenario: synthesize target text in a reference voice, then score
timbre preservation (SIM) + intelligibility (CER) against ground truth.

Fills the lab's biggest gap — the dubbing/TTS stage had no GT-anchored metric, only
``e2e-dub``'s intrinsic honest score (which under-reports the timbre band). Follows
seed-tts-eval: SIM via speaker-embedding cosine, intelligibility via ASR
re-transcription. **SIM is the primary metric** — it is exactly the timbre
dimension nothing else in the lab measures and the intrinsic score hides.

invoke:  ``tts_synth`` worker (clone) → ``translip transcribe`` (re-transcribe the synth).
score:   CER/WER(reference text, re-transcript) + SIM(reference voice, synth).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..core.invoke import Invoker, StageResult
from ..core.sample import Sample
from ..core.scenario import Scenario, register_scenario
from ..metrics.speaker import speaker_similarity
from ..metrics.text import cer as cer_metric
from ..metrics.text import wer as wer_metric


class TtsCloneScenario(Scenario):
    name = "tts-clone"
    primary_metric_key = "sim"
    higher_is_better = True

    def required_gt(self) -> list[str]:
        return ["clone_text"]

    def _reference_wav(self, sample: Sample) -> Path:
        return Path(sample.ground_truth.clone_ref_wav or sample.media_path)

    def input_paths(self, sample: Sample) -> list[str | Path]:
        return [sample.media_path, self._reference_wav(sample)]

    def invoke(self, sample, work_dir, invoker, *, config, timeout, log_path) -> StageResult:
        text = sample.ground_truth.clone_text or ""
        ref = self._reference_wav(sample)
        lang = config.get("language") or sample.meta.get("lang") or "zh"
        synth = work_dir / "synth.wav"
        r_tts = invoker.module(
            "translip_lab.tts_synth",
            ["--text", text, "--reference", str(ref), "--output", str(synth),
             "--language", str(lang), "--backend", str(config.get("tts_backend", "qwen3tts"))],
            timeout=timeout, log_path=work_dir / "tts.log",
        )
        if not r_tts.ok:
            return r_tts
        synth_path = r_tts.outputs.get("synth_wav", str(synth))
        asr_args = ["--input", synth_path, "--output-dir", str(work_dir / "transcribe"),
                    "--language", str(lang)]
        for flag, key in (("--asr-backend", "asr_backend"), ("--asr-model", "asr_model"),
                          ("--device", "device")):
            if config.get(key):
                asr_args += [flag, str(config[key])]
        r_asr = invoker.translip("transcribe", asr_args, timeout=timeout, log_path=log_path)
        # Carry the synth path into the scored outputs even though ASR didn't emit it.
        r_asr.outputs = {**r_asr.outputs, "synth_wav": synth_path}
        return r_asr

    def score(self, sample, work_dir, stage, config) -> dict[str, Any]:
        outputs = (stage.outputs or {}) if stage else {}
        synth = outputs.get("synth_wav")
        if not synth or not Path(synth).is_file():
            raise RuntimeError("tts-clone produced no readable synth_wav")
        seg_path = outputs.get("segments")
        if not seg_path or not Path(seg_path).is_file():
            raise RuntimeError("transcribe of the synth produced no readable segments JSON")
        segments = json.loads(Path(seg_path).read_text(encoding="utf-8")).get("segments", [])
        hyp_text = "".join(str(s.get("text", "")) for s in segments)
        target = sample.ground_truth.clone_text or ""

        cer_value = cer_metric(target, hyp_text)
        result: dict[str, Any] = {
            "cer": round(cer_value, 4),
            "wer": round(wer_metric(target, hyp_text), 4),
            "intelligibility": round(1.0 - min(cer_value, 1.0), 4),
            "reference_char_count": len("".join(target.split())),
        }
        sim = speaker_similarity(self._reference_wav(sample), synth,
                                 device=str(config.get("device", "auto")))
        result["sim"] = round(sim["sim"], 4) if isinstance(sim.get("sim"), (int, float)) else None
        if sim.get("note"):
            result["sim_note"] = sim["note"]
        return result

    def corpus_metrics(self, metrics_list):
        out: dict[str, Any] = {}
        total_ref = sum((m.get("reference_char_count") or 0) for m in metrics_list)
        if total_ref > 0:
            total_edits = sum((m.get("cer") or 0.0) * (m.get("reference_char_count") or 0)
                              for m in metrics_list)
            out["cer_micro"] = round(total_edits / total_ref, 4)
        sims = [m["sim"] for m in metrics_list if isinstance(m.get("sim"), (int, float))]
        if sims:
            out["sim_mean"] = round(sum(sims) / len(sims), 4)
        return out


register_scenario(TtsCloneScenario())
