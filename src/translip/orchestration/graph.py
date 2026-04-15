from __future__ import annotations

import heapq
from dataclasses import dataclass

from ..types import WorkflowNodeGroup, WorkflowNodeName, WorkflowTemplateName
from .nodes import NODE_REGISTRY
from .templates import TEMPLATE_REGISTRY


@dataclass(frozen=True, slots=True)
class ResolvedNode:
    name: WorkflowNodeName
    required: bool
    group: WorkflowNodeGroup


@dataclass(frozen=True, slots=True)
class ResolvedTemplatePlan:
    template_id: WorkflowTemplateName
    node_order: list[WorkflowNodeName]
    nodes: dict[WorkflowNodeName, ResolvedNode]


def _collect_nodes(node_name: WorkflowNodeName, selected: set[WorkflowNodeName]) -> None:
    if node_name in selected:
        return
    selected.add(node_name)
    for dependency in NODE_REGISTRY[node_name].dependencies:
        _collect_nodes(dependency, selected)


def _topological_order(selected: set[WorkflowNodeName]) -> list[WorkflowNodeName]:
    indegree = {name: 0 for name in selected}
    dependents: dict[WorkflowNodeName, list[WorkflowNodeName]] = {name: [] for name in selected}
    for name in selected:
        for dependency in NODE_REGISTRY[name].dependencies:
            if dependency not in selected:
                continue
            indegree[name] += 1
            dependents[dependency].append(name)

    ready: list[tuple[int, WorkflowNodeName]] = [
        (NODE_REGISTRY[name].sequence_hint, name) for name, degree in indegree.items() if degree == 0
    ]
    heapq.heapify(ready)
    ordered: list[WorkflowNodeName] = []

    while ready:
        _, node_name = heapq.heappop(ready)
        ordered.append(node_name)
        for dependent in dependents[node_name]:
            indegree[dependent] -= 1
            if indegree[dependent] == 0:
                heapq.heappush(ready, (NODE_REGISTRY[dependent].sequence_hint, dependent))

    if len(ordered) != len(selected):
        raise ValueError("Workflow graph contains an unresolved cycle")
    return ordered


def resolve_template_plan(template_id: WorkflowTemplateName) -> ResolvedTemplatePlan:
    if template_id not in TEMPLATE_REGISTRY:
        raise ValueError(f"Unsupported workflow template: {template_id}")

    template = TEMPLATE_REGISTRY[template_id]
    selected: set[WorkflowNodeName] = set()
    for node_name in template.selected_nodes:
        _collect_nodes(node_name, selected)

    node_order = _topological_order(selected)
    nodes = {
        node_name: ResolvedNode(
            name=node_name,
            required=node_name in template.required_nodes,
            group=NODE_REGISTRY[node_name].group,
        )
        for node_name in node_order
    }
    return ResolvedTemplatePlan(template_id=template.template_id, node_order=node_order, nodes=nodes)


__all__ = ["ResolvedNode", "ResolvedTemplatePlan", "resolve_template_plan"]
