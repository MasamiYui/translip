from __future__ import annotations

from typing import Any

from .graph import resolve_template_plan


def _edge_state(source_status: str, target_status: str) -> str:
    completed_statuses = {"succeeded", "cached"}
    if source_status in completed_statuses and target_status == "running":
        return "active"
    if source_status in completed_statuses and target_status in {"succeeded", "cached", "failed", "skipped"}:
        return "completed"
    if target_status == "failed":
        return "blocked"
    return "inactive"


def build_workflow_graph_payload(manifest_payload: dict[str, Any]) -> dict[str, Any]:
    template_id = str(manifest_payload["template_id"])
    plan = resolve_template_plan(template_id)
    node_rows = {
        str(row.get("node_name") or row.get("stage_name")): row
        for row in manifest_payload.get("nodes", manifest_payload.get("stages", []))
        if isinstance(row, dict)
    }
    nodes = [
        {
            "id": node_name,
            "label": node_name,
            "group": plan.nodes[node_name].group,
            "required": plan.nodes[node_name].required,
            "status": node_rows.get(node_name, {}).get("status", "pending"),
            "progress_percent": node_rows.get(node_name, {}).get("progress_percent", 0.0),
            "manifest_path": node_rows.get(node_name, {}).get("manifest_path"),
            "log_path": node_rows.get(node_name, {}).get("log_path"),
            "error_message": node_rows.get(node_name, {}).get("error_message"),
        }
        for node_name in plan.node_order
    ]
    edges = [
        {
            "from": dependency,
            "to": node_name,
            "state": _edge_state(
                str(node_rows.get(dependency, {}).get("status", "pending")),
                str(node_rows.get(node_name, {}).get("status", "pending")),
            ),
        }
        for node_name in plan.node_order
        for dependency in plan.dependencies_for(node_name)
        if dependency in plan.nodes
    ]
    return {
        "workflow": {
            "template_id": plan.template_id,
            "status": manifest_payload.get("status", "pending"),
        },
        "nodes": nodes,
        "edges": edges,
    }


__all__ = ["build_workflow_graph_payload"]
