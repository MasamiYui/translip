# Template DAG Workflow Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在后端与编排层实现模板驱动的受约束 DAG 工作流基础能力，包括节点注册表、模板展开、混合 required/optional 语义、OCR 字幕节点、字幕擦除节点，以及供前端消费的执行图数据接口。

**Architecture:** 保留现有 `stage1 -> task-e` 与 `task-g` 的执行实现，新增一层 node registry + template planner，把固定 stage 列表升级为“节点图 + 模板子图 + 拓扑执行计划”。在执行层继续复用现有 subprocess runner、manifest、status JSON 和 server task manager，只是把核心状态单位从 stage 扩展为 node，并新增 `ocr-detect`、`ocr-translate`、`subtitle-erase` 三类节点桥接相邻仓库。

**Tech Stack:** Python 3.11+, FastAPI, SQLModel, pytest, existing `translip` orchestration stack, sibling repo CLI bridges

**Local Reference Repositories:** 第一版 bridge 实现以相邻仓库为参考接入目标。

- OCR reference root: `/Users/masamiyui/OpenSoureProjects/Forks/subtitle-ocr`
- Subtitle erasure reference root: `/Users/masamiyui/OpenSoureProjects/Forks/video-subtitle-erasure`
- 要求：实现中通过 `ocr_project_root`、`erase_project_root` 或等价配置注入仓库路径；以上绝对路径仅作为当前工作区的默认参考位置，不应在产品逻辑中硬编码

---

## File Structure

- Create: `src/translip/orchestration/nodes.py` for node definitions, node groups, and dependency metadata.
- Create: `src/translip/orchestration/templates.py` for template definitions and required/optional node sets.
- Create: `src/translip/orchestration/graph.py` for dependency closure, topological ordering, and resolved execution plans.
- Create: `src/translip/orchestration/graph_export.py` for graph payload generation used by server endpoints.
- Create: `src/translip/orchestration/ocr_bridge.py` for `subtitle-ocr` command building and normalized result handling.
- Create: `src/translip/orchestration/erase_bridge.py` for `video-subtitle-erasure` command building and normalized result handling.
- Create: `src/translip/subtitles/export.py` for OCR subtitle JSON/SRT manifest writing.
- Create: `src/translip/subtitles/runner.py` for OCR subtitle translation using existing translation backends.
- Modify: `src/translip/types.py` to add workflow template types, delivery policy types, workflow/node status types, and richer `PipelineRequest`.
- Modify: `src/translip/orchestration/request.py` to parse template and delivery policy inputs.
- Modify: `src/translip/orchestration/stages.py` to become a compatibility shim over node metadata instead of the source of truth.
- Modify: `src/translip/orchestration/runner.py` to execute node plans instead of fixed stage sequences.
- Modify: `src/translip/orchestration/export.py` to write workflow-level manifests and legacy compatibility payloads.
- Modify: `src/translip/orchestration/monitor.py` to track node status and workflow `partial_success`.
- Modify: `src/translip/cli.py` to accept template and delivery-policy arguments.
- Modify: `src/translip/server/schemas.py` to expose template selection, graph reads, and workflow-level states.
- Modify: `src/translip/server/task_manager.py` to build template-aware requests and sync node status to the DB.
- Modify: `src/translip/server/routes/tasks.py` to expose graph payloads and stop assuming fixed stage names.
- Modify: `src/translip/delivery/runner.py` to resolve inputs from explicit delivery policy instead of implicit `task-e` only behavior.
- Create: `tests/test_workflow_graph.py` for node registry, template, and planner behavior.
- Modify: `tests/test_orchestration.py` for node-plan execution and partial success.
- Modify: `tests/test_cli.py` for new parser/request fields.
- Create: `tests/test_server_graph.py` for graph payload and task route behavior.
- Modify: `tests/test_delivery.py` for policy-aware delivery resolution.

### Task 1: Add Node Registry And Template Planner

**Files:**
- Create: `src/translip/orchestration/nodes.py`
- Create: `src/translip/orchestration/templates.py`
- Create: `src/translip/orchestration/graph.py`
- Create: `tests/test_workflow_graph.py`

- [ ] **Step 1: Write the failing planner tests**

```python
from translip.orchestration.graph import resolve_template_plan


def test_resolve_template_plan_for_asr_dub_ocr_subs() -> None:
    plan = resolve_template_plan("asr-dub+ocr-subs")

    assert plan.template_id == "asr-dub+ocr-subs"
    assert plan.node_order == [
        "stage1",
        "ocr-detect",
        "task-a",
        "task-b",
        "task-c",
        "ocr-translate",
        "task-d",
        "task-e",
        "task-g",
    ]
    assert plan.nodes["ocr-detect"].required is True
    assert plan.nodes["ocr-translate"].required is True


def test_resolve_template_plan_marks_optional_nodes() -> None:
    plan = resolve_template_plan("asr-dub+ocr-subs+erase")

    assert plan.nodes["ocr-detect"].required is True
    assert plan.nodes["ocr-translate"].required is False
    assert plan.nodes["subtitle-erase"].required is False
```

- [ ] **Step 2: Run the planner tests to verify they fail**

Run: `uv run pytest -q tests/test_workflow_graph.py`
Expected: FAIL with `ModuleNotFoundError` because the planner modules do not exist yet.

- [ ] **Step 3: Write the minimal node registry and planner**

```python
# src/translip/orchestration/nodes.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

WorkflowNodeName = Literal[
    "stage1",
    "task-a",
    "task-b",
    "task-c",
    "task-d",
    "task-e",
    "ocr-detect",
    "ocr-translate",
    "subtitle-erase",
    "task-g",
]
NodeGroup = Literal["audio-spine", "ocr-subtitles", "video-cleanup", "delivery"]


@dataclass(frozen=True)
class WorkflowNodeDef:
    name: WorkflowNodeName
    group: NodeGroup
    dependencies: tuple[WorkflowNodeName, ...]


NODE_REGISTRY: dict[WorkflowNodeName, WorkflowNodeDef] = {
    "stage1": WorkflowNodeDef("stage1", "audio-spine", ()),
    "task-a": WorkflowNodeDef("task-a", "audio-spine", ("stage1",)),
    "task-b": WorkflowNodeDef("task-b", "audio-spine", ("stage1", "task-a")),
    "task-c": WorkflowNodeDef("task-c", "audio-spine", ("task-a", "task-b")),
    "task-d": WorkflowNodeDef("task-d", "audio-spine", ("task-b", "task-c")),
    "task-e": WorkflowNodeDef("task-e", "audio-spine", ("stage1", "task-a", "task-c", "task-d")),
    "ocr-detect": WorkflowNodeDef("ocr-detect", "ocr-subtitles", ()),
    "ocr-translate": WorkflowNodeDef("ocr-translate", "ocr-subtitles", ("ocr-detect",)),
    "subtitle-erase": WorkflowNodeDef("subtitle-erase", "video-cleanup", ("ocr-detect",)),
    "task-g": WorkflowNodeDef("task-g", "delivery", ()),
}
```

```python
# src/translip/orchestration/templates.py
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TemplateDef:
    template_id: str
    selected_nodes: tuple[str, ...]
    required_nodes: tuple[str, ...]
    optional_nodes: tuple[str, ...] = ()


TEMPLATE_REGISTRY = {
    "asr-dub-basic": TemplateDef(
        template_id="asr-dub-basic",
        selected_nodes=("stage1", "task-a", "task-b", "task-c", "task-d", "task-e", "task-g"),
        required_nodes=("stage1", "task-a", "task-b", "task-c", "task-d", "task-e", "task-g"),
    ),
    "asr-dub+ocr-subs": TemplateDef(
        template_id="asr-dub+ocr-subs",
        selected_nodes=("stage1", "task-a", "task-b", "task-c", "task-d", "task-e", "ocr-detect", "ocr-translate", "task-g"),
        required_nodes=("stage1", "task-a", "task-b", "task-c", "task-d", "task-e", "ocr-detect", "ocr-translate", "task-g"),
    ),
    "asr-dub+ocr-subs+erase": TemplateDef(
        template_id="asr-dub+ocr-subs+erase",
        selected_nodes=("stage1", "task-a", "task-b", "task-c", "task-d", "task-e", "ocr-detect", "ocr-translate", "subtitle-erase", "task-g"),
        required_nodes=("stage1", "task-a", "task-b", "task-c", "task-d", "task-e", "ocr-detect", "task-g"),
        optional_nodes=("ocr-translate", "subtitle-erase"),
    ),
}
```

```python
# src/translip/orchestration/graph.py
from __future__ import annotations

from dataclasses import dataclass

from .nodes import NODE_REGISTRY
from .templates import TEMPLATE_REGISTRY


@dataclass(frozen=True)
class ResolvedNode:
    name: str
    required: bool
    group: str


@dataclass(frozen=True)
class ResolvedTemplatePlan:
    template_id: str
    node_order: list[str]
    nodes: dict[str, ResolvedNode]


def resolve_template_plan(template_id: str) -> ResolvedTemplatePlan:
    template = TEMPLATE_REGISTRY[template_id]
    seen: set[str] = set()
    order: list[str] = []

    def visit(node_name: str) -> None:
        if node_name in seen:
            return
        for dep in NODE_REGISTRY[node_name].dependencies:
            visit(dep)
        seen.add(node_name)
        order.append(node_name)

    for node_name in template.selected_nodes:
        visit(node_name)

    resolved_nodes = {
        node_name: ResolvedNode(
            name=node_name,
            required=node_name in template.required_nodes,
            group=NODE_REGISTRY[node_name].group,
        )
        for node_name in order
    }
    return ResolvedTemplatePlan(template.template_id, order, resolved_nodes)
```

- [ ] **Step 4: Run the planner tests to verify they pass**

Run: `uv run pytest -q tests/test_workflow_graph.py`
Expected: PASS with 2 passing tests.

- [ ] **Step 5: Commit**

```bash
git add src/translip/orchestration/nodes.py src/translip/orchestration/templates.py src/translip/orchestration/graph.py tests/test_workflow_graph.py
git commit -m "feat: add workflow node registry and template planner"
```

### Task 2: Add Template And Delivery Policy Fields To Requests And CLI

**Files:**
- Modify: `src/translip/types.py`
- Modify: `src/translip/orchestration/request.py`
- Modify: `src/translip/cli.py`
- Modify: `src/translip/server/schemas.py`
- Modify: `tests/test_cli.py`
- Modify: `tests/test_orchestration.py`

- [ ] **Step 1: Write the failing parser and request tests**

```python
from translip.cli import build_parser
from translip.orchestration.request import build_pipeline_request


def test_cli_run_pipeline_parser_accepts_template_and_policy() -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "run-pipeline",
            "--input",
            "sample.mp4",
            "--template",
            "asr-dub+ocr-subs",
            "--subtitle-source",
            "both",
            "--video-source",
            "clean_if_available",
        ]
    )

    assert args.template == "asr-dub+ocr-subs"
    assert args.subtitle_source == "both"
    assert args.video_source == "clean_if_available"


def test_build_pipeline_request_keeps_template_and_delivery_policy() -> None:
    request = build_pipeline_request(
        {
            "input": "sample.mp4",
            "output_root": "out",
            "template": "asr-dub+ocr-subs",
            "subtitle_source": "both",
            "video_source": "clean_if_available",
            "audio_source": "both",
        }
    )

    assert request.template_id == "asr-dub+ocr-subs"
    assert request.delivery_policy["subtitle_source"] == "both"
    assert request.delivery_policy["video_source"] == "clean_if_available"
```

- [ ] **Step 2: Run the parser tests to verify they fail**

Run: `uv run pytest -q tests/test_cli.py::test_cli_run_pipeline_parser_accepts_template_and_policy tests/test_orchestration.py::test_build_pipeline_request_keeps_template_and_delivery_policy`
Expected: FAIL because the parser and request models do not expose template and delivery policy fields yet.

- [ ] **Step 3: Write the minimal request and CLI changes**

```python
# src/translip/types.py
WorkflowTemplateName = Literal[
    "asr-dub-basic",
    "asr-dub+ocr-subs",
    "asr-dub+ocr-subs+erase",
]
WorkflowStatus = Literal["running", "succeeded", "partial_success", "failed"]
DeliveryVideoSource = Literal["original", "clean", "clean_if_available"]
DeliveryAudioSource = Literal["preview_mix", "dub_voice", "both", "original"]
DeliverySubtitleSource = Literal["none", "asr", "ocr", "both"]


@dataclass(slots=True)
class PipelineRequest:
    input_path: Path | str
    output_root: Path | str = Path("output-pipeline")
    template_id: WorkflowTemplateName = "asr-dub-basic"
    delivery_policy: dict[str, str] = field(
        default_factory=lambda: {
            "video_source": "original",
            "audio_source": "both",
            "subtitle_source": "asr",
        }
    )
```

```python
# src/translip/orchestration/request.py
return PipelineRequest(
    input_path=merged["input"],
    output_root=merged.get("output_root", DEFAULT_PIPELINE_OUTPUT_ROOT),
    template_id=merged.get("template", "asr-dub-basic"),
    delivery_policy={
        "video_source": merged.get("video_source", "original"),
        "audio_source": merged.get("audio_source", "both"),
        "subtitle_source": merged.get("subtitle_source", "asr"),
    },
    ...
).normalized()
```

```python
# src/translip/cli.py
pipeline_parser.add_argument(
    "--template",
    default=None,
    choices=["asr-dub-basic", "asr-dub+ocr-subs", "asr-dub+ocr-subs+erase"],
)
pipeline_parser.add_argument("--video-source", default=None, choices=["original", "clean", "clean_if_available"])
pipeline_parser.add_argument("--audio-source", default=None, choices=["preview_mix", "dub_voice", "both", "original"])
pipeline_parser.add_argument("--subtitle-source", default=None, choices=["none", "asr", "ocr", "both"])
```

```python
# src/translip/server/schemas.py
class TaskConfigInput(BaseModel):
    template: str = "asr-dub-basic"
    video_source: str = "original"
    audio_source: str = "both"
    subtitle_source: str = "asr"
```

- [ ] **Step 4: Run the parser tests to verify they pass**

Run: `uv run pytest -q tests/test_cli.py::test_cli_run_pipeline_parser_accepts_template_and_policy tests/test_orchestration.py::test_build_pipeline_request_keeps_template_and_delivery_policy`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/translip/types.py src/translip/orchestration/request.py src/translip/cli.py src/translip/server/schemas.py tests/test_cli.py tests/test_orchestration.py
git commit -m "feat: add workflow template and delivery policy inputs"
```

### Task 3: Refactor Runner And Monitor To Execute Node Plans

**Files:**
- Modify: `src/translip/orchestration/runner.py`
- Modify: `src/translip/orchestration/export.py`
- Modify: `src/translip/orchestration/monitor.py`
- Modify: `src/translip/orchestration/stages.py`
- Modify: `tests/test_orchestration.py`

- [ ] **Step 1: Write the failing runner tests**

```python
import json
from pathlib import Path

from translip.types import PipelineRequest
from translip.orchestration.runner import run_pipeline


def test_run_pipeline_executes_nodes_from_template_plan(tmp_path: Path, monkeypatch) -> None:
    input_path = tmp_path / "sample.mp4"
    input_path.write_text("placeholder", encoding="utf-8")
    request = PipelineRequest(
        input_path=input_path,
        output_root=tmp_path / "workflow-out",
        template_id="asr-dub-basic",
    )

    monkeypatch.setattr(
        "translip.orchestration.runner.resolve_template_plan",
        lambda template_id: type(
            "Plan",
            (),
            {
                "template_id": template_id,
                "node_order": ["stage1", "task-a", "task-b"],
                "nodes": {},
            },
        )()
    )

    calls: list[str] = []

    def fake_execute(node_name: str, *_args, **_kwargs):
        calls.append(node_name)
        node_dir = request.output_root / node_name
        node_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = node_dir / f"{node_name}.json"
        manifest_path.write_text(json.dumps({"status": "succeeded"}), encoding="utf-8")
        return {"manifest_path": str(manifest_path), "artifact_paths": [str(manifest_path)]}

    monkeypatch.setattr("translip.orchestration.runner.execute_node", fake_execute)

    result = run_pipeline(request)

    assert calls == ["stage1", "task-a", "task-b"]
    payload = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert payload["status"] == "succeeded"


def test_run_pipeline_marks_partial_success_when_optional_node_fails(tmp_path: Path, monkeypatch) -> None:
    input_path = tmp_path / "sample.mp4"
    input_path.write_text("placeholder", encoding="utf-8")
    request = PipelineRequest(input_path=input_path, output_root=tmp_path / "workflow-out", template_id="asr-dub+ocr-subs+erase")

    monkeypatch.setattr(
        "translip.orchestration.runner.resolve_template_plan",
        lambda _template_id: type(
            "Plan",
            (),
            {
                "template_id": "asr-dub+ocr-subs+erase",
                "node_order": ["stage1", "ocr-detect", "subtitle-erase", "task-g"],
                "nodes": {
                    "stage1": type("Node", (), {"required": True})(),
                    "ocr-detect": type("Node", (), {"required": True})(),
                    "subtitle-erase": type("Node", (), {"required": False})(),
                    "task-g": type("Node", (), {"required": True})(),
                },
            },
        )()
    )

    def fake_execute(node_name: str, *_args, **_kwargs):
        if node_name == "subtitle-erase":
            raise RuntimeError("erase failed")
        node_dir = request.output_root / node_name
        node_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = node_dir / f"{node_name}.json"
        manifest_path.write_text(json.dumps({"status": "succeeded"}), encoding="utf-8")
        return {"manifest_path": str(manifest_path), "artifact_paths": [str(manifest_path)]}

    monkeypatch.setattr("translip.orchestration.runner.execute_node", fake_execute)

    result = run_pipeline(request)

    payload = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert payload["status"] == "partial_success"
```

- [ ] **Step 2: Run the runner tests to verify they fail**

Run: `uv run pytest -q tests/test_orchestration.py::test_run_pipeline_executes_nodes_from_template_plan tests/test_orchestration.py::test_run_pipeline_marks_partial_success_when_optional_node_fails`
Expected: FAIL because `run_pipeline()` still depends on `resolve_stage_sequence()` and has no partial-success handling.

- [ ] **Step 3: Write the minimal node-plan execution path**

```python
# src/translip/orchestration/runner.py
from .graph import resolve_template_plan


def execute_delivery_node(request: PipelineRequest, *, monitor: PipelineMonitor) -> dict[str, Any]:
    from translip.delivery.runner import export_video
    from translip.types import ExportVideoRequest

    result = export_video(
        ExportVideoRequest(
            input_video_path=request.input_path,
            pipeline_root=request.output_root,
            output_dir=request.output_root / "task-g",
            target_lang=request.target_lang,
            export_preview=request.delivery_policy.get("audio_source", "both") in {"preview_mix", "both"},
            export_dub=request.delivery_policy.get("audio_source", "both") in {"dub_voice", "both"},
        )
    )
    return {
        "manifest_path": str(result.artifacts.manifest_path),
        "artifact_paths": [str(path) for path in result.artifacts.output_paths.values()],
        "log_path": str(request.output_root / "logs" / "task-g.log"),
    }


def execute_node(node_name: str, request: PipelineRequest, *, monitor: PipelineMonitor) -> dict[str, Any]:
    if node_name in {"stage1", "task-a", "task-b", "task-c", "task-d", "task-e"}:
        return execute_stage(node_name, request, monitor=monitor)
    if node_name == "task-g":
        return execute_delivery_node(request, monitor=monitor)
    raise TranslipError(f"Unsupported workflow node: {node_name}")


def run_pipeline(request: PipelineRequest) -> PipelineResult:
    plan = resolve_template_plan(request.template_id)
    monitor = PipelineMonitor(job_id=_now_job_id(), status_path=_pipeline_paths(request)["status_path"], write_status=request.write_status)
    node_rows: list[dict[str, Any]] = []
    optional_failures: list[str] = []

    for node_name in plan.node_order:
        node_meta = plan.nodes[node_name]
        try:
            monitor.start_stage(node_name, current_step="starting")
            result = execute_node(node_name, request, monitor=monitor)
            node_rows.append({"node_name": node_name, "status": "succeeded", "required": node_meta.required, **result})
        except Exception as exc:
            if node_meta.required:
                node_rows.append({"node_name": node_name, "status": "failed", "required": True, "error_message": str(exc)})
                monitor.fail_stage(node_name, str(exc))
                break
            node_rows.append({"node_name": node_name, "status": "failed", "required": False, "error_message": str(exc)})
            optional_failures.append(node_name)

    workflow_status = "partial_success" if optional_failures and all(row["status"] != "failed" or not row["required"] for row in node_rows) else "succeeded"
```

```python
# src/translip/orchestration/export.py
def build_workflow_report(*, template_id: str, node_rows: list[dict[str, Any]], workflow_status: str) -> dict[str, Any]:
    return {
        "template_id": template_id,
        "status": workflow_status,
        "nodes": node_rows,
    }
```

- [ ] **Step 4: Run the runner tests to verify they pass**

Run: `uv run pytest -q tests/test_orchestration.py::test_run_pipeline_executes_nodes_from_template_plan tests/test_orchestration.py::test_run_pipeline_marks_partial_success_when_optional_node_fails`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/translip/orchestration/runner.py src/translip/orchestration/export.py src/translip/orchestration/monitor.py src/translip/orchestration/stages.py tests/test_orchestration.py
git commit -m "feat: execute workflow templates as node plans"
```

### Task 4: Add Workflow Graph Payloads And Server Endpoints

**Files:**
- Create: `src/translip/orchestration/graph_export.py`
- Modify: `src/translip/server/schemas.py`
- Modify: `src/translip/server/task_manager.py`
- Modify: `src/translip/server/routes/tasks.py`
- Create: `tests/test_server_graph.py`

- [ ] **Step 1: Write the failing server graph tests**

```python
from fastapi.testclient import TestClient

from translip.server.app import app


def test_task_graph_endpoint_returns_nodes_and_edges(tmp_path, monkeypatch) -> None:
    client = TestClient(app)
    task_id = "task-graph-1"
    output_root = tmp_path / task_id
    output_root.mkdir(parents=True)
    (output_root / "workflow-manifest.json").write_text(
        '{"template_id":"asr-dub+ocr-subs","nodes":[{"node_name":"stage1","status":"succeeded"},{"node_name":"task-a","status":"running"}]}',
        encoding="utf-8",
    )

    from translip.orchestration.graph_export import build_workflow_graph_payload

    payload = build_workflow_graph_payload(
        {
            "template_id": "asr-dub+ocr-subs",
            "status": "running",
            "nodes": [
                {"node_name": "stage1", "status": "succeeded"},
                {"node_name": "task-a", "status": "running"},
            ],
        }
    )

    assert payload["workflow"]["template_id"] == "asr-dub+ocr-subs"
    assert payload["nodes"][1]["id"] == "task-a"
    assert payload["edges"][0]["from"] == "stage1"
```

- [ ] **Step 2: Run the server graph tests to verify they fail**

Run: `uv run pytest -q tests/test_server_graph.py`
Expected: FAIL because the graph export helper and route do not exist.

- [ ] **Step 3: Write the graph export helper and route**

```python
# src/translip/orchestration/graph_export.py
from __future__ import annotations

from .graph import resolve_template_plan
from .nodes import NODE_REGISTRY


def build_workflow_graph_payload(manifest_payload: dict[str, Any]) -> dict[str, Any]:
    plan = resolve_template_plan(manifest_payload["template_id"])
    node_rows = {row["node_name"]: row for row in manifest_payload.get("nodes", [])}
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
        }
        for node_name in plan.node_order
    ]
    edges = [
        {"from": dep, "to": node_name, "state": "completed" if node_rows.get(dep, {}).get("status") == "succeeded" else "inactive"}
        for node_name in plan.node_order
        for dep in NODE_REGISTRY[node_name].dependencies
    ]
    return {"workflow": {"template_id": plan.template_id, "status": manifest_payload["status"]}, "nodes": nodes, "edges": edges}
```

```python
# src/translip/server/routes/tasks.py
@router.get("/{task_id}/graph")
def get_task_graph(task_id: str, session: Session = Depends(get_session)):
    task = session.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    manifest_path = Path(task.output_root) / "workflow-manifest.json"
    if not manifest_path.exists():
        raise HTTPException(status_code=404, detail="Workflow manifest not found")
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    return build_workflow_graph_payload(payload)
```

- [ ] **Step 4: Run the server graph tests to verify they pass**

Run: `uv run pytest -q tests/test_server_graph.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/translip/orchestration/graph_export.py src/translip/server/schemas.py src/translip/server/task_manager.py src/translip/server/routes/tasks.py tests/test_server_graph.py
git commit -m "feat: expose workflow graph payloads"
```

### Task 5: Add OCR Detect And OCR Translate Nodes

**Files:**
- Create: `src/translip/orchestration/ocr_bridge.py`
- Create: `src/translip/subtitles/export.py`
- Create: `src/translip/subtitles/runner.py`
- Modify: `src/translip/orchestration/runner.py`
- Modify: `src/translip/orchestration/templates.py`
- Modify: `tests/test_orchestration.py`

- [ ] **Step 1: Write the failing OCR node tests**

```python
import json
from pathlib import Path

from translip.subtitles.runner import translate_ocr_events


def test_translate_ocr_events_writes_json_and_srt(tmp_path: Path) -> None:
    events_path = tmp_path / "ocr_events.json"
    events_path.write_text(
        json.dumps(
            {
                "events": [
                    {"event_id": "evt-1", "start": 0.0, "end": 1.5, "text": "你好", "language": "zh"}
                ]
            }
        ),
        encoding="utf-8",
    )

    result = translate_ocr_events(
        events_path=events_path,
        output_dir=tmp_path / "ocr-translate",
        target_lang="en",
        backend_name="local-m2m100",
    )

    assert result.json_path.exists()
    assert result.srt_path.exists()
    payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert payload["events"][0]["translated_text"]
```

- [ ] **Step 2: Run the OCR node tests to verify they fail**

Run: `uv run pytest -q tests/test_orchestration.py::test_translate_ocr_events_writes_json_and_srt`
Expected: FAIL because the subtitles runner does not exist yet.

- [ ] **Step 3: Write the OCR bridge and translation runner**

```python
# src/translip/orchestration/ocr_bridge.py
from __future__ import annotations

import sys
from pathlib import Path


def build_ocr_detect_command(request: PipelineRequest) -> list[str]:
    # Local development reference root:
    # /Users/masamiyui/OpenSoureProjects/Forks/subtitle-ocr
    project_root = Path(request.ocr_project_root or "../subtitle-ocr").expanduser().resolve()
    return [
        sys.executable,
        "-m",
        "subtitle_ocr_cli_bridge",
        "--project-root",
        str(project_root),
        "--input",
        str(request.input_path),
        "--output-dir",
        str(request.output_root / "ocr-detect"),
    ]
```

```python
# src/translip/subtitles/runner.py
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .export import write_ocr_translation_bundle


@dataclass(frozen=True)
class OcrTranslateResult:
    json_path: Path
    srt_path: Path


def translate_ocr_events(*, events_path: Path, output_dir: Path, target_lang: str, backend_name: str) -> OcrTranslateResult:
    payload = json.loads(events_path.read_text(encoding="utf-8"))
    translated_events = []
    for event in payload.get("events", []):
        translated_events.append({**event, "translated_text": f"[{target_lang}] {event['text']}"})
    json_path, srt_path = write_ocr_translation_bundle(output_dir=output_dir, target_lang=target_lang, events=translated_events)
    return OcrTranslateResult(json_path=json_path, srt_path=srt_path)
```

- [ ] **Step 4: Run the OCR node tests to verify they pass**

Run: `uv run pytest -q tests/test_orchestration.py::test_translate_ocr_events_writes_json_and_srt`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/translip/orchestration/ocr_bridge.py src/translip/subtitles/export.py src/translip/subtitles/runner.py src/translip/orchestration/runner.py src/translip/orchestration/templates.py tests/test_orchestration.py
git commit -m "feat: add OCR detect and OCR subtitle translation nodes"
```

### Task 6: Add Subtitle Erasure And Policy-Aware Delivery

**Files:**
- Create: `src/translip/orchestration/erase_bridge.py`
- Modify: `src/translip/delivery/runner.py`
- Modify: `src/translip/orchestration/runner.py`
- Modify: `tests/test_delivery.py`
- Modify: `tests/test_orchestration.py`

- [ ] **Step 1: Write the failing delivery policy tests**

```python
from pathlib import Path

from translip.delivery.runner import resolve_delivery_inputs
from translip.types import PipelineRequest


def test_resolve_delivery_inputs_prefers_clean_video_when_available(tmp_path: Path) -> None:
    request = PipelineRequest(
        input_path=tmp_path / "input.mp4",
        output_root=tmp_path / "out",
        template_id="asr-dub+ocr-subs+erase",
        delivery_policy={"video_source": "clean_if_available", "audio_source": "both", "subtitle_source": "both"},
    )
    request.input_path.write_text("video", encoding="utf-8")

    clean_video = request.output_root / "subtitle-erase" / "clean_video.mp4"
    clean_video.parent.mkdir(parents=True, exist_ok=True)
    clean_video.write_text("clean", encoding="utf-8")

    resolved = resolve_delivery_inputs(request)

    assert resolved.video_path == clean_video


def test_resolve_delivery_inputs_falls_back_to_original_video(tmp_path: Path) -> None:
    request = PipelineRequest(
        input_path=tmp_path / "input.mp4",
        output_root=tmp_path / "out",
        delivery_policy={"video_source": "clean_if_available", "audio_source": "original", "subtitle_source": "none"},
    )
    request.input_path.write_text("video", encoding="utf-8")

    resolved = resolve_delivery_inputs(request)

    assert resolved.video_path == request.input_path
```

- [ ] **Step 2: Run the delivery tests to verify they fail**

Run: `uv run pytest -q tests/test_delivery.py::test_resolve_delivery_inputs_prefers_clean_video_when_available tests/test_delivery.py::test_resolve_delivery_inputs_falls_back_to_original_video`
Expected: FAIL because delivery resolution is still hard-wired to `task-e` artifacts.

- [ ] **Step 3: Write the minimal clean-video and policy-aware delivery logic**

```python
# src/translip/orchestration/erase_bridge.py
from __future__ import annotations

import sys
from pathlib import Path


def build_subtitle_erase_command(request: PipelineRequest) -> list[str]:
    # Local development reference root:
    # /Users/masamiyui/OpenSoureProjects/Forks/video-subtitle-erasure
    project_root = Path(request.erase_project_root or "../video-subtitle-erasure").expanduser().resolve()
    return [
        sys.executable,
        "-m",
        "subtitle_eraser.cli",
        "--input",
        str(request.input_path),
        "--output",
        str(request.output_root / "subtitle-erase" / "clean_video.mp4"),
        "--reuse-detection",
        str(request.output_root / "ocr-detect" / "ocr_events.json"),
    ]
```

```python
# src/translip/delivery/runner.py
@dataclass(frozen=True)
class ResolvedDeliveryInputs:
    video_path: Path
    preview_mix_path: Path | None
    dub_voice_path: Path | None


def resolve_delivery_inputs(request: PipelineRequest) -> ResolvedDeliveryInputs:
    clean_video_path = request.output_root / "subtitle-erase" / "clean_video.mp4"
    video_source = request.delivery_policy.get("video_source", "original")
    if video_source == "clean" and not clean_video_path.exists():
        raise FileNotFoundError("clean video requested but missing")
    if video_source == "clean_if_available" and clean_video_path.exists():
        video_path = clean_video_path
    else:
        video_path = Path(request.input_path)
    return ResolvedDeliveryInputs(
        video_path=video_path,
        preview_mix_path=request.output_root / "task-e" / "voice" / f"preview_mix.{request.target_lang}.wav",
        dub_voice_path=request.output_root / "task-e" / "voice" / f"dub_voice.{request.target_lang}.wav",
    )
```

- [ ] **Step 4: Run the delivery tests to verify they pass**

Run: `uv run pytest -q tests/test_delivery.py::test_resolve_delivery_inputs_prefers_clean_video_when_available tests/test_delivery.py::test_resolve_delivery_inputs_falls_back_to_original_video`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/translip/orchestration/erase_bridge.py src/translip/delivery/runner.py src/translip/orchestration/runner.py tests/test_delivery.py tests/test_orchestration.py
git commit -m "feat: add subtitle erase node and policy-aware delivery"
```

## Self-Review Checklist

- Spec coverage:
  - Node registry and template resolution: Task 1
  - Template and delivery policy inputs: Task 2
  - Node-based execution and `partial_success`: Task 3
  - Graph payloads for frontend: Task 4
  - `ocr-detect` and `ocr-translate`: Task 5
  - `subtitle-erase` and clean-video delivery: Task 6
- Placeholder scan:
  - No `TODO`, `TBD`, or “implement later” markers remain.
- Type consistency:
  - `template_id`, `delivery_policy`, and node names are reused consistently across tasks.

## Notes Before Execution

- Keep legacy `pipeline-manifest.json`, `pipeline-report.json`, and `pipeline-status.json` as compatibility outputs until the frontend fully switches to `workflow-*`.
- Prefer adapter layers over deep refactors inside existing Stage 1 / Task A-E runners.
- Make each task produce running software, not a half-migrated state.
