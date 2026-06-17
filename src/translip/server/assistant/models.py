"""Pydantic DTOs for the natural-language assistant.

A *plan* is what the DeepSeek planner produces: an ordered list of atomic-tool
steps plus how each step's file inputs are wired (from an uploaded file or from a
previous step's named output). A *run* is the live execution state of a plan,
assembled by merging the persisted run row with the underlying atomic-tool jobs.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

BindingSource = Literal["upload", "step"]


class Binding(BaseModel):
    """How a single file parameter of a step is supplied.

    - ``source="upload"``: take ``upload_index``-th uploaded file.
    - ``source="step"``: take the artifact named by the ``output`` result-key of
      the step with ``step_id`` (e.g. separation's ``voice_file``). When
      ``output`` is omitted the step's sole artifact is used.
    """

    source: BindingSource
    upload_index: Optional[int] = None
    step_id: Optional[str] = None
    output: Optional[str] = None


class PlanStep(BaseModel):
    id: str = Field(description="Stable step id, referenced by edges and bindings")
    tool_id: str = Field(description="Atomic tool id from the catalog")
    title: str = Field(default="", description="Short human label for the diagram node")
    rationale: str = Field(default="", description="Why this step is needed")
    params: dict[str, Any] = Field(
        default_factory=dict, description="Non-file parameters for the tool"
    )
    inputs: dict[str, Binding] = Field(
        default_factory=dict, description="File-parameter name -> binding"
    )


class StepEdge(BaseModel):
    source: str
    target: str


class AssistantPlan(BaseModel):
    summary: str = Field(default="", description="Natural-language explanation of the plan")
    steps: list[PlanStep] = Field(default_factory=list)
    edges: list[StepEdge] = Field(default_factory=list)


# --- API request bodies -----------------------------------------------------


class PlanRequest(BaseModel):
    message: str
    file_ids: list[str] = Field(default_factory=list)
    filenames: list[str] = Field(
        default_factory=list, description="Optional names parallel to file_ids, for planner context"
    )


class ExecuteRequest(BaseModel):
    plan: AssistantPlan
    file_ids: list[str] = Field(default_factory=list)
    conversation_id: Optional[str] = None


# --- Run / execution state --------------------------------------------------

RunStatus = Literal["pending", "running", "completed", "failed", "cancelled"]


class StepArtifact(BaseModel):
    filename: str
    download_url: str
    file_id: Optional[str] = None
    size_bytes: int = 0
    content_type: str = ""


class RunStepState(BaseModel):
    id: str
    tool_id: str
    title: str = ""
    job_id: Optional[str] = None
    status: str = "pending"
    progress_percent: float = 0.0
    current_step: Optional[str] = None
    error_message: Optional[str] = None
    artifacts: list[StepArtifact] = Field(default_factory=list)


class RunState(BaseModel):
    run_id: str
    status: RunStatus
    message: str = ""
    summary: str = ""
    steps: list[RunStepState] = Field(default_factory=list)
    error_message: Optional[str] = None
