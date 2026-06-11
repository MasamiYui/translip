from __future__ import annotations

from dataclasses import dataclass

from ..types import WorkflowNodeName, WorkflowTemplateName


@dataclass(frozen=True, slots=True)
class TemplateDef:
    template_id: WorkflowTemplateName
    selected_nodes: tuple[WorkflowNodeName, ...]
    required_nodes: tuple[WorkflowNodeName, ...]
    optional_nodes: tuple[WorkflowNodeName, ...] = ()
    dependency_overrides: dict[WorkflowNodeName, tuple[WorkflowNodeName, ...]] | None = None


TEMPLATE_REGISTRY: dict[WorkflowTemplateName, TemplateDef] = {
    "asr-dub-basic": TemplateDef(
        template_id="asr-dub-basic",
        selected_nodes=("stage1", "task-a", "task-b", "task-c", "task-d", "task-e", "task-g"),
        required_nodes=("stage1", "task-a", "task-b", "task-c", "task-d", "task-e", "task-g"),
    ),
    "asr-dub+visual": TemplateDef(
        template_id="asr-dub+visual",
        selected_nodes=("stage1", "task-a", "task-b", "visual-context", "task-c", "task-d", "task-e", "task-g"),
        required_nodes=("stage1", "task-a", "task-b", "task-c", "task-d", "task-e", "task-g"),
        # Optional: translation degrades gracefully without visual context, so a
        # missing vision backend must not fail the whole pipeline.
        optional_nodes=("visual-context",),
    ),
    "asr-dub+ocr-subs": TemplateDef(
        template_id="asr-dub+ocr-subs",
        selected_nodes=(
            "stage1",
            "task-a",
            "asr-ocr-correct",
            "task-b",
            "task-c",
            "task-d",
            "task-e",
            "ocr-detect",
            "ocr-translate",
            "task-g",
        ),
        required_nodes=(
            "stage1",
            "task-a",
            "asr-ocr-correct",
            "task-b",
            "task-c",
            "task-d",
            "task-e",
            "ocr-detect",
            "ocr-translate",
            "task-g",
        ),
        dependency_overrides={"task-b": ("asr-ocr-correct",)},
    ),
    "asr-dub+ocr-subs+erase": TemplateDef(
        template_id="asr-dub+ocr-subs+erase",
        selected_nodes=(
            "stage1",
            "task-a",
            "asr-ocr-correct",
            "task-b",
            "task-c",
            "task-d",
            "task-e",
            "ocr-detect",
            "ocr-translate",
            "subtitle-erase",
            "erase-qc",
            "task-g",
        ),
        required_nodes=("stage1", "task-a", "asr-ocr-correct", "task-b", "task-c", "task-d", "task-e", "ocr-detect", "task-g"),
        # erase-qc is opt-in at runtime (erase_qc_enabled) and a pure report —
        # a missing vision backend or QC failure never blocks delivery.
        optional_nodes=("ocr-translate", "subtitle-erase", "erase-qc"),
        dependency_overrides={"task-b": ("asr-ocr-correct",)},
    ),
}


__all__ = ["TEMPLATE_REGISTRY", "TemplateDef"]
