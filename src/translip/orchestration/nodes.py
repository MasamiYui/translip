from __future__ import annotations

from dataclasses import dataclass

from ..types import WorkflowNodeGroup, WorkflowNodeName


@dataclass(frozen=True, slots=True)
class WorkflowNodeDef:
    name: WorkflowNodeName
    group: WorkflowNodeGroup
    dependencies: tuple[WorkflowNodeName, ...]
    sequence_hint: int


NODE_REGISTRY: dict[WorkflowNodeName, WorkflowNodeDef] = {
    "separation": WorkflowNodeDef("separation", "audio-spine", (), 10),
    "ocr-detect": WorkflowNodeDef("ocr-detect", "ocr-subtitles", (), 20),
    "transcription": WorkflowNodeDef("transcription", "audio-spine", ("separation",), 30),
    "asr-ocr-correct": WorkflowNodeDef("asr-ocr-correct", "audio-spine", ("transcription", "ocr-detect"), 35),
    "speaker-registry": WorkflowNodeDef("speaker-registry", "audio-spine", ("separation", "transcription"), 40),
    # Runs after asr-ocr-correct (35) in templates that include it, so it sees
    # the corrected segments translation will consume (matching by time overlap).
    "visual-context": WorkflowNodeDef("visual-context", "visual-perception", ("transcription",), 45),
    "translation": WorkflowNodeDef("translation", "audio-spine", ("transcription", "speaker-registry"), 50),
    "ocr-translate": WorkflowNodeDef("ocr-translate", "ocr-subtitles", ("ocr-detect",), 60),
    "synthesis": WorkflowNodeDef("synthesis", "audio-spine", ("speaker-registry", "translation"), 70),
    "render": WorkflowNodeDef("render", "audio-spine", ("separation", "transcription", "translation", "synthesis"), 80),
    "subtitle-erase": WorkflowNodeDef("subtitle-erase", "video-cleanup", ("ocr-detect",), 90),
    # Vision QC of the erased video: samples the original subtitle spans on
    # clean_video.mp4 and reports leftover text / inpainting artifacts.
    # Pure report — never blocks the pipeline (optional in templates).
    "erase-qc": WorkflowNodeDef("erase-qc", "visual-perception", ("subtitle-erase",), 95),
    "delivery": WorkflowNodeDef("delivery", "delivery", (), 100),
}


__all__ = ["NODE_REGISTRY", "WorkflowNodeDef"]
