"""MagicData-RAMC adapter (OpenSLR SLR123) — Mandarin spontaneous *conversation*,
ASR (CER) + diarization (DER) GT in one corpus.

Why this corpus: the lab's open CER/DER GT was meetings only (AISHELL-4 / AliMeeting)
plus film/TV ASR (WenetSpeech-Drama, no speaker GT). RAMC is 180h of two-party phone
conversations with manual transcripts AND per-speaker voice-activity timestamps, so
it extends both CER and DER into the spontaneous-dialogue domain — far closer to
film/TV dialogue dynamics than meetings. Official baselines: CER 19.1% (test),
DER 7.96% (collar 0.25). License: CC BY-NC-ND 4.0 (academic/eval, not commercial).

**Format — NOT TextGrid.** RAMC ships per-conversation ``.txt`` transcripts whose
segments are::

    [start,end] <speaker_id> <gender,dialect> <transcription>
    e.g.  [1.319,6.691] G00000140 女,普通话 爱数智慧语音采集二零一九年十一月六日

plus ``SPKINFO.txt`` / ``UTTERANCEINFO.txt`` metadata. This adapter parses those
segments into ``(start, end, speaker, text)`` and reuses the shared RTTM/SRT
emitters. Built to the published format examples; **confirm against one real
conversation file before trusting real-data numbers** — the parser is isolated
here (``parse_ramc_transcript``) for easy adjustment.

Place the extracted corpus under ``<datasets>/magicdata-ramc/<subset>/`` (subset =
``train`` | ``dev`` | ``test``). The adapter finds every ``*.wav`` and its sibling
``<stem>.txt`` anywhere under that dir, so it tolerates flat or WAV/TXT-split layouts.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ..config import LabConfig
from ..core.sample import GroundTruth, Sample, SampleManifest
from .base import DatasetAdapter, register_dataset
from .textgrid import to_rttm, to_srt

_SEGMENT = re.compile(r"\[\s*([0-9]+(?:\.[0-9]+)?)\s*,\s*([0-9]+(?:\.[0-9]+)?)\s*\]")
# A gender,dialect attribute token like 女,普通话 / 男,四川话 — distinct from transcription text.
_ATTRS = re.compile(r"^[男女][^\s,]*,[^\s]+$")
_METADATA_NAMES = {"SPKINFO.txt", "UTTERANCEINFO.txt"}


def parse_ramc_transcript(path: str | Path) -> list[tuple[float, float, str, str]]:
    """Parse a RAMC ``.txt`` into ``[(start, end, speaker, text), ...]``, sorted by time.

    Splits on each ``[start,end]`` marker and reads the trailing
    ``<speaker_id> [<gender,dialect>] <text>``. The optional demographic token is
    dropped from the reference text; whitespace inside the (Chinese) text is
    collapsed — CER ignores whitespace anyway. Zero-length / empty segments drop.
    """
    content = Path(path).read_text(encoding="utf-8", errors="replace")
    marks = list(_SEGMENT.finditer(content))
    intervals: list[tuple[float, float, str, str]] = []
    for i, m in enumerate(marks):
        start, end = float(m.group(1)), float(m.group(2))
        chunk = content[m.end(): (marks[i + 1].start() if i + 1 < len(marks) else len(content))]
        tokens = chunk.split()
        if len(tokens) < 2:
            continue  # need at least a speaker + one text token
        speaker = tokens[0]
        rest = tokens[1:]
        if rest and _ATTRS.match(rest[0]):
            rest = rest[1:]  # strip the gender,dialect attribute
        text = "".join(rest).strip()
        if end > start and text:
            intervals.append((start, end, speaker, text))
    intervals.sort(key=lambda x: (x[0], x[1]))
    return intervals


@register_dataset
class MagicDataRamcDataset(DatasetAdapter):
    name = "magicdata-ramc"

    def __init__(self, config: LabConfig, *, subset: str = "test", audio_ext: str = ".wav",
                 lang: str = "zh", **params: Any) -> None:
        super().__init__(config, subset=subset, audio_ext=audio_ext, lang=lang, **params)
        self.subset = subset
        self.audio_ext = audio_ext if audio_ext.startswith(".") else f".{audio_ext}"
        self.lang = lang
        self._base = config.datasets_dir / "magicdata-ramc" / subset

    @property
    def root(self) -> Path:
        return self.config.datasets_dir / "magicdata-ramc"

    def _cache_dir(self) -> Path:
        d = self.config.cache_dir / "datasets" / self.name / self.subset
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _index_transcripts(self) -> dict[str, Path]:
        index: dict[str, Path] = {}
        for txt in self._base.rglob("*.txt"):
            if txt.name in _METADATA_NAMES:
                continue
            index.setdefault(txt.stem, txt)
        return index

    def normalize(self) -> SampleManifest:
        if not self._base.exists():
            raise FileNotFoundError(
                f"MagicData-RAMC subset not found: {self._base}. Extract the OpenSLR "
                "SLR123 archive there (see `translip-lab datasets` for the layout)."
            )
        transcripts = self._index_transcripts()
        cache = self._cache_dir()
        samples: list[Sample] = []
        for audio in sorted(self._base.rglob(f"*{self.audio_ext}")):
            gt = GroundTruth()
            txt = transcripts.get(audio.stem)
            if txt is not None:
                intervals = parse_ramc_transcript(txt)
                out_dir = cache / audio.stem
                out_dir.mkdir(parents=True, exist_ok=True)
                rttm_path = out_dir / "ref.rttm"
                rttm_path.write_text(to_rttm(intervals, audio.stem), encoding="utf-8")
                srt_path = out_dir / "ref.srt"
                srt_path.write_text(to_srt(intervals), encoding="utf-8")
                gt.rttm = rttm_path
                gt.transcript_srt = srt_path
            samples.append(Sample(
                sample_id=audio.stem, media_path=audio, ground_truth=gt,
                meta={"lang": self.lang, "source": self.name, "subset": self.subset},
            ))
        return SampleManifest(dataset=self.name, samples=samples,
                              meta={"base": str(self._base), "subset": self.subset, "lang": self.lang})

    def describe(self) -> dict[str, Any]:
        d = super().describe()
        d.update({
            "license": "CC BY-NC-ND 4.0 (OpenSLR SLR123; academic/eval, not commercial)",
            "provides": ["asr (CER)", "diarization (DER)"],
            "domain": "spontaneous 2-party phone conversation (16 kHz)",
            "expected_layout": f"{self.root}/<subset>/**/*.wav + sibling <stem>.txt"
                               " ([start,end] speaker gender,dialect text)",
            "baseline": "CER 19.1% / DER 7.96% (collar 0.25), test set",
            "caveat": "transcript format built to published examples — confirm against a real .txt first",
        })
        return d
