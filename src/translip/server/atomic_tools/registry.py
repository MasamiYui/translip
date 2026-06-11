from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ToolCategory = Literal["audio", "speech", "video"]


@dataclass(slots=True)
class ToolSpec:
    tool_id: str
    name_zh: str
    name_en: str
    description_zh: str
    description_en: str
    category: ToolCategory
    icon: str
    accept_formats: list[str]
    max_file_size_mb: int = 500
    max_files: int = 1
    # Heavy tools (multi-GB model inference) are additionally serialized on a
    # dedicated single slot in the job manager so two of them never run at
    # once on a 16 GB host (vision + erase together would exhaust memory).
    heavy: bool = False


TOOL_REGISTRY: dict[str, ToolSpec] = {}
ADAPTER_REGISTRY: dict[str, type] = {}


def register_tool(spec: ToolSpec, adapter_cls: type | None = None) -> None:
    TOOL_REGISTRY[spec.tool_id] = spec
    if adapter_cls is not None:
        ADAPTER_REGISTRY[spec.tool_id] = adapter_cls


def get_all_tools() -> list[ToolSpec]:
    return list(TOOL_REGISTRY.values())


def get_tool_spec(tool_id: str) -> ToolSpec:
    return TOOL_REGISTRY[tool_id]


def create_adapter(tool_id: str):
    adapter_cls = ADAPTER_REGISTRY.get(tool_id)
    if adapter_cls is None:
        raise KeyError(f"No adapter registered for tool: {tool_id}")
    return adapter_cls()
