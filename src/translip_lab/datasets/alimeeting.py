"""AliMeeting / M2MeT adapter (OpenSLR SLR119) — Mandarin meetings, ASR + diar GT.

Place under ``<datasets>/alimeeting/``. The M2MeT release lays out subsets as
``<subset>/audio_dir/*.wav`` + ``<subset>/textgrid_dir/*.TextGrid`` (e.g.
``Eval_Ali/Eval_Ali_far``). Override ``subset`` for Train/Test or near-field.
License: CC BY-SA 4.0. The official challenge scores DER (Track 1) and
multi-speaker CER (Track 2).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..config import LabConfig
from .base import register_dataset
from .textgrid_folder import TextGridFolderDataset


@register_dataset
class AliMeetingDataset(TextGridFolderDataset):
    name = "alimeeting"

    def __init__(self, config: LabConfig, *, subset: str = "Eval_Ali/Eval_Ali_far",
                 audio_subdir: str = "audio_dir", textgrid_subdir: str = "textgrid_dir",
                 audio_ext: str = ".wav", **params: Any) -> None:
        base = config.datasets_dir / "alimeeting" / subset
        super().__init__(
            config,
            audio_dir=str(base / audio_subdir),
            textgrid_dir=str(base / textgrid_subdir),
            lang="zh",
            audio_ext=audio_ext,
            **params,
        )
        self._declared_root = config.datasets_dir / "alimeeting"
        self.subset = subset

    @property
    def root(self) -> Path:
        return self._declared_root

    def describe(self) -> dict[str, Any]:
        d = super().describe()
        d.update({
            "license": "CC BY-SA 4.0 (OpenSLR SLR119)",
            "provides": ["asr (CER)", "diarization (DER)"],
            "expected_layout": f"{self.root}/<subset>/{{audio_dir,textgrid_dir}}/*.wav|*.TextGrid",
        })
        return d
