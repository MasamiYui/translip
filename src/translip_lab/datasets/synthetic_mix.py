"""Synthetic voice+music mixer — known stems for separation SI-SDR.

There are no clean dialogue stems for film/TV, so we mix a syllable-modulated
harmonic "voice" with a chord+noise "background" into ``mix.wav`` and keep both
stems as GT. This validates the separation plumbing and the metric; for *real*
separation numbers, supply real stems via the ``folder`` dataset
(``<stem>.voice.wav`` + ``<stem>.background.wav``).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from ..config import LabConfig
from ..core.sample import GroundTruth, Sample, SampleManifest
from .base import DatasetAdapter, register_dataset


def generate_mix(out_dir: Path, *, duration: float = 3.0, sr: int = 16000, seed: int = 0) -> dict[str, Path]:
    import soundfile as sf

    out_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)

    f0 = 160.0
    syllable_env = 0.5 * (1.0 + np.sin(2 * np.pi * 3.0 * t))  # ~3 Hz syllable rate
    voice = syllable_env * (
        0.6 * np.sin(2 * np.pi * f0 * t)
        + 0.3 * np.sin(2 * np.pi * 2 * f0 * t)
        + 0.15 * np.sin(2 * np.pi * 3 * f0 * t)
    )
    voice *= 0.5

    background = (
        0.2 * np.sin(2 * np.pi * 220.0 * t)
        + 0.2 * np.sin(2 * np.pi * 277.0 * t)
        + 0.2 * np.sin(2 * np.pi * 330.0 * t)
        + 0.02 * rng.standard_normal(t.shape)
    )
    background *= 0.5

    mix = voice + background
    peak = float(np.max(np.abs(mix))) or 1.0
    mix = mix / peak * 0.9

    paths = {
        "voice": out_dir / "voice.wav",
        "background": out_dir / "background.wav",
        "mix": out_dir / "mix.wav",
    }
    sf.write(paths["voice"], voice.astype(np.float32), sr)
    sf.write(paths["background"], background.astype(np.float32), sr)
    sf.write(paths["mix"], mix.astype(np.float32), sr)
    return paths


@register_dataset
class SyntheticMixDataset(DatasetAdapter):
    name = "synthetic-mix"

    def __init__(self, config: LabConfig, *, clips: int = 1, duration: float = 3.0,
                 sr: int = 16000, **params: Any) -> None:
        super().__init__(config, clips=clips, duration=duration, sr=sr, **params)
        self.clips = clips
        self.duration = duration
        self.sr = sr

    def normalize(self) -> SampleManifest:
        out_root = self.config.cache_dir / "synthetic-mix"
        samples: list[Sample] = []
        for i in range(self.clips):
            paths = generate_mix(out_root / f"clip_{i:03d}", duration=self.duration, sr=self.sr, seed=i)
            gt = GroundTruth(clean_stems={"voice": str(paths["voice"]), "background": str(paths["background"])})
            samples.append(Sample(
                sample_id=f"synth_mix_{i:03d}", media_path=paths["mix"], ground_truth=gt,
                meta={"lang": "zh", "source": "synthetic", "duration_sec": self.duration},
            ))
        return SampleManifest(dataset=self.name, samples=samples, meta={"generated": True})
