"""Natural-language assistant: DeepSeek plans + chains the atomic tools."""

from __future__ import annotations

from .catalog import build_tool_catalog
from .executor import AssistantRunManager, run_manager
from .models import (
    AssistantPlan,
    AvailableFileRef,
    Clarification,
    ConversationTurn,
    ExecuteRequest,
    PlanRequest,
    PlanResult,
    RunState,
)
from .planner import generate_plan, parse_planner_response

__all__ = [
    "AssistantPlan",
    "AssistantRunManager",
    "AvailableFileRef",
    "Clarification",
    "ConversationTurn",
    "ExecuteRequest",
    "PlanRequest",
    "PlanResult",
    "RunState",
    "build_tool_catalog",
    "generate_plan",
    "parse_planner_response",
    "run_manager",
]
