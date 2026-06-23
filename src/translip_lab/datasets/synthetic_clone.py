"""Synthetic voice-clone cases — (reference voice, target text) pairs for tts-clone.

No public Chinese film/TV clone-eval set exists, so we fabricate a deterministic
"speaker" (a formant-structured harmonic tone whose timbre is fixed by
``speaker_seed``) as the reference voice and pair it with a target sentence. This
validates the ``tts-clone`` plumbing + SIM/CER metrics offline (no model, no
download), exactly like ``synthetic-mix`` / ``synthetic-subtitle`` do for their
stages. For *real* numbers feed real voice samples via the ``folder`` dataset
(``<stem>.clone.txt`` + optional ``<stem>.ref.wav``).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from ..config import LabConfig
from ..core.sample import GroundTruth, Sample, SampleManifest
from .base import DatasetAdapter, register_dataset

# Short, varied Mandarin lines (dialogue-like) so CER reflects real-ish phonetics.
_SENTENCES = (
    "今天的天气非常好，我们一起去公园散步吧。",
    "他缓缓转过身，眼神里写满了不舍。",
    "这件事我会负责到底，请你放心。",
    "列车即将到站，请乘客们提前做好准备。",
    "她轻声说，谢谢你一直陪在我身边。",
)


def synth_voice(seed: int, *, duration: float = 4.0, sr: int = 16000) -> np.ndarray:
    """A deterministic 'speaker': harmonic tone whose pitch + formant weights depend on seed.

    Same seed → same timbre (high SIM); different seed → different timbre (lower
    SIM). Pure numpy, so embeddings of two same-seed clips land close together.
    """
    rng = np.random.default_rng(seed)
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    f0 = 110.0 + (seed % 7) * 14.0  # speaker-dependent fundamental
    weights = 0.6 + 0.4 * np.abs(rng.standard_normal(4))  # speaker-dependent harmonic timbre
    syllable = 0.5 * (1.0 + np.sin(2 * np.pi * 3.3 * t))  # ~3.3 Hz syllable envelope
    voice = np.zeros_like(t)
    for k, base_amp in enumerate((0.6, 0.3, 0.18, 0.1), start=1):
        voice += base_amp * weights[k - 1] * np.sin(2 * np.pi * f0 * k * t)
    voice *= syllable
    peak = float(np.max(np.abs(voice))) or 1.0
    return (voice / peak * 0.7).astype(np.float32)


def generate_clone_case(out_dir: Path, *, index: int = 0, speaker_seed: int = 0,
                        duration: float = 4.0, sr: int = 16000) -> dict[str, Any]:
    """Write ``prompt.wav`` (the reference voice) and return its path + target text."""
    import soundfile as sf

    out_dir.mkdir(parents=True, exist_ok=True)
    prompt = out_dir / "prompt.wav"
    sf.write(prompt, synth_voice(speaker_seed, duration=duration, sr=sr), sr)
    return {"prompt": prompt, "text": _SENTENCES[index % len(_SENTENCES)]}


@register_dataset
class SyntheticCloneDataset(DatasetAdapter):
    name = "synthetic-clone"

    def __init__(self, config: LabConfig, *, clips: int = 2, duration: float = 4.0,
                 sr: int = 16000, **params: Any) -> None:
        super().__init__(config, clips=clips, duration=duration, sr=sr, **params)
        self.clips = clips
        self.duration = duration
        self.sr = sr

    def normalize(self) -> SampleManifest:
        out_root = self.config.cache_dir / "synthetic-clone"
        samples: list[Sample] = []
        for i in range(self.clips):
            case = generate_clone_case(out_root / f"clip_{i:03d}", index=i, speaker_seed=i,
                                       duration=self.duration, sr=self.sr)
            gt = GroundTruth(clone_text=case["text"], clone_ref_wav=case["prompt"])
            samples.append(Sample(
                sample_id=f"synth_clone_{i:03d}", media_path=case["prompt"], ground_truth=gt,
                meta={"lang": "zh", "source": "synthetic", "duration_sec": self.duration,
                      "target_text": case["text"]},
            ))
        return SampleManifest(dataset=self.name, samples=samples, meta={"generated": True})
