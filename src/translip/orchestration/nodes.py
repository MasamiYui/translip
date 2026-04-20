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
    "stage1": WorkflowNodeDef("stage1", "audio-spine", (), 10),
    "ocr-detect": WorkflowNodeDef("ocr-detect", "ocr-subtitles", (), 20),
    "task-a": WorkflowNodeDef("task-a", "audio-spine", ("stage1",), 30),
    "asr-ocr-correct": WorkflowNodeDef("asr-ocr-correct", "audio-spine", ("task-a", "ocr-detect"), 35),
    "task-b": WorkflowNodeDef("task-b", "audio-spine", ("stage1", "task-a"), 40),
    "task-c": WorkflowNodeDef("task-c", "audio-spine", ("task-a", "task-b"), 50),
    "ocr-translate": WorkflowNodeDef("ocr-translate", "ocr-subtitles", ("ocr-detect",), 60),
    "task-d": WorkflowNodeDef("task-d", "audio-spine", ("task-b", "task-c"), 70),
    "task-e": WorkflowNodeDef("task-e", "audio-spine", ("stage1", "task-a", "task-c", "task-d"), 80),
    "subtitle-erase": WorkflowNodeDef("subtitle-erase", "video-cleanup", ("ocr-detect",), 90),
    "task-g": WorkflowNodeDef("task-g", "delivery", (), 100),
}


__all__ = ["NODE_REGISTRY", "WorkflowNodeDef"]
