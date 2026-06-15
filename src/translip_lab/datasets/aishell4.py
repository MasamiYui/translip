"""AISHELL-4 adapter (OpenSLR SLR111) — real Mandarin meetings, ASR + diarization GT.

Place the corpus under ``<datasets>/aishell4/``. AISHELL-4 ships ``.flac`` audio
with per-meeting ``.TextGrid`` (and often ``.rttm``); point ``audio_subdir`` /
``textgrid_subdir`` at the right folders if your extraction differs. License:
CC BY-SA 4.0. See README for download.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..config import LabConfig
from .base import register_dataset
from .textgrid_folder import TextGridFolderDataset


@register_dataset
class Aishell4Dataset(TextGridFolderDataset):
    name = "aishell4"

    def __init__(self, config: LabConfig, *, subset: str = "test",
                 audio_subdir: str = "wav", textgrid_subdir: str = "TextGrid",
                 audio_ext: str = ".flac", **params: Any) -> None:
        base = config.datasets_dir / "aishell4" / subset
        super().__init__(
            config,
            audio_dir=str(base / audio_subdir),
            textgrid_dir=str(base / textgrid_subdir),
            lang="zh",
            audio_ext=audio_ext,
            **params,
        )
        self._declared_root = config.datasets_dir / "aishell4"
        self.subset = subset

    @property
    def root(self) -> Path:
        return self._declared_root

    def describe(self) -> dict[str, Any]:
        d = super().describe()
        d.update({
            "license": "CC BY-SA 4.0 (OpenSLR SLR111)",
            "provides": ["asr (CER)", "diarization (DER)"],
            "expected_layout": f"{self.root}/<subset>/{{wav,TextGrid}}/*.flac|*.TextGrid",
        })
        return d
