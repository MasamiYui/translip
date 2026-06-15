"""Audio + TextGrid (or sidecar RTTM) folder → ASR + diarization GT.

For each audio file it prefers an existing ``<stem>.rttm`` (AISHELL-4 ships these)
and otherwise converts ``<stem>.TextGrid`` (AliMeeting). Derived RTTM/SRT are
cached under the lab cache dir, so the source corpus is never modified.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..config import LabConfig
from ..core.sample import GroundTruth, Sample, SampleManifest
from .base import DatasetAdapter, register_dataset
from .textgrid import parse_textgrid, to_rttm, to_srt


@register_dataset
class TextGridFolderDataset(DatasetAdapter):
    name = "textgrid-folder"

    def __init__(self, config: LabConfig, *, audio_dir: str, textgrid_dir: str | None = None,
                 lang: str = "zh", audio_ext: str = ".wav", **params: Any) -> None:
        super().__init__(config, audio_dir=audio_dir, textgrid_dir=textgrid_dir,
                         lang=lang, audio_ext=audio_ext, **params)
        self.audio_dir = Path(audio_dir).expanduser()
        self.textgrid_dir = Path(textgrid_dir).expanduser() if textgrid_dir else self.audio_dir
        self.lang = lang
        self.audio_ext = audio_ext if audio_ext.startswith(".") else f".{audio_ext}"

    @property
    def root(self) -> Path:
        return self.audio_dir

    def _cache_dir(self) -> Path:
        d = self.config.cache_dir / "datasets" / self.name
        d.mkdir(parents=True, exist_ok=True)
        return d

    def normalize(self) -> SampleManifest:
        if not self.audio_dir.exists():
            raise FileNotFoundError(
                f"audio dir not found: {self.audio_dir}. Place the corpus there "
                "(see `translip-lab datasets` for the expected layout)."
            )
        cache = self._cache_dir()
        samples: list[Sample] = []
        for audio in sorted(self.audio_dir.rglob(f"*{self.audio_ext}")):
            gt = GroundTruth()
            existing_rttm = self._find_sibling(audio, ".rttm")
            if existing_rttm is not None:
                gt.rttm = existing_rttm
            tg = self._find_sibling(audio, ".TextGrid") or self._find_sibling(audio, ".textgrid")
            if tg is not None:
                intervals = parse_textgrid(tg)
                out_dir = cache / audio.stem
                out_dir.mkdir(parents=True, exist_ok=True)
                if gt.rttm is None:
                    rttm_path = out_dir / "ref.rttm"
                    rttm_path.write_text(to_rttm(intervals, audio.stem), encoding="utf-8")
                    gt.rttm = rttm_path
                srt_path = out_dir / "ref.srt"
                srt_path.write_text(to_srt(intervals), encoding="utf-8")
                gt.transcript_srt = srt_path
            samples.append(Sample(
                sample_id=audio.stem, media_path=audio, ground_truth=gt,
                meta={"lang": self.lang, "source": self.name},
            ))
        return SampleManifest(dataset=self.name, samples=samples,
                              meta={"audio_dir": str(self.audio_dir), "lang": self.lang})

    def _find_sibling(self, audio: Path, suffix: str) -> Path | None:
        for base in (self.textgrid_dir, self.audio_dir, audio.parent):
            candidate = base / (audio.stem + suffix)
            if candidate.is_file():
                return candidate
        return None
