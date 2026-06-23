"""Generic "bring your own" folder dataset: media + sidecar ground truth.

For each media file ``<stem>.<ext>`` under the root, sidecars by stem provide GT:
  <stem>.srt            → reference subtitles (ASR CER)
  <stem>.rttm           → reference diarization (DER)
  <stem>.boxes.json     → subtitle box GT (OCR detection F1)
  <stem>.clean.mp4      → subtitle-free reference video (erase PSNR/SSIM)
  <stem>.voice.wav + <stem>.background.wav → clean stems (separation SI-SDR)
  <stem>.clone.txt      → target text for voice-clone TTS (tts-clone CER); the media
                          itself is the reference voice unless <stem>.ref.wav is present
  <stem>.ref.wav        → explicit target-voice reference (tts-clone SIM)

This is how you turn ANY corpus (or your own clips) into a quantifiable bench
once you drop the references next to the media.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..config import LabConfig
from ..core.sample import GroundTruth, Sample, SampleManifest
from .base import DatasetAdapter, register_dataset

_MEDIA_EXTS = (".mp4", ".mkv", ".mov", ".webm", ".wav", ".mp3", ".flac", ".m4a", ".aac", ".ogg")
_GT_MEDIA_SUFFIXES = (".voice", ".background", ".clean", ".ref")


@register_dataset
class FolderDataset(DatasetAdapter):
    name = "folder"

    def __init__(self, config: LabConfig, *, root: str | None = None, lang: str = "zh",
                 media_exts: tuple[str, ...] = _MEDIA_EXTS, **params: Any) -> None:
        super().__init__(config, root=root, lang=lang, **params)
        self._root = Path(root).expanduser() if root else config.datasets_dir / "folder"
        self.lang = lang
        self.media_exts = tuple(e.lower() for e in media_exts)

    @property
    def root(self) -> Path:
        return self._root

    def normalize(self) -> SampleManifest:
        if not self._root.exists():
            raise FileNotFoundError(
                f"folder dataset root not found: {self._root}. "
                "Create it and drop media + sidecar GT files inside."
            )
        samples: list[Sample] = []
        for media in sorted(self._root.rglob("*")):
            if not media.is_file() or media.suffix.lower() not in self.media_exts:
                continue
            if any(media.stem.endswith(sfx) for sfx in _GT_MEDIA_SUFFIXES):
                continue  # this is a GT sidecar, not an input sample
            stem_path = media.with_suffix("")
            gt = GroundTruth()
            srt = media.with_suffix(".srt")
            if srt.is_file():
                gt.transcript_srt = srt
            rttm = media.with_suffix(".rttm")
            if rttm.is_file():
                gt.rttm = rttm
            boxes = Path(f"{stem_path}.boxes.json")
            if boxes.is_file():
                gt.subtitle_boxes = boxes
            clean = Path(f"{stem_path}.clean.mp4")
            if clean.is_file():
                gt.clean_video = clean
            voice = Path(f"{stem_path}.voice.wav")
            background = Path(f"{stem_path}.background.wav")
            if voice.is_file() and background.is_file():
                gt.clean_stems = {"voice": str(voice), "background": str(background)}
            clone_txt = Path(f"{stem_path}.clone.txt")
            if clone_txt.is_file():
                gt.clone_text = clone_txt.read_text(encoding="utf-8").strip()
                ref_wav = Path(f"{stem_path}.ref.wav")
                gt.clone_ref_wav = ref_wav if ref_wav.is_file() else media
            samples.append(Sample(
                sample_id=media.stem, media_path=media, ground_truth=gt,
                meta={"lang": self.lang, "source": "folder"},
            ))
        return SampleManifest(dataset=self.name, samples=samples,
                              meta={"root": str(self._root), "lang": self.lang})
