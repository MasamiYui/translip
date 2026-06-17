from __future__ import annotations

import time
from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient
from sqlmodel import SQLModel, create_engine

from translip.exceptions import BackendUnavailableError


def _isolated_engine(tmp_path: Path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'assistant-routes.db'}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    return engine


class StubProbe:
    def validate_params(self, params: dict) -> dict:
        return dict(params)

    def run(self, params: dict, input_dir: Path, output_dir: Path, on_progress) -> dict:
        on_progress(60.0, "probing")
        (output_dir / "probe.json").write_text("{}", encoding="utf-8")
        return {"report_file": "probe.json"}


_PLAN_PAYLOAD = {
    "summary": "探测媒体信息",
    "steps": [
        {
            "id": "probe",
            "tool_id": "probe",
            "title": "媒体探测",
            "params": {},
            "inputs": {"file_id": {"source": "upload", "upload_index": 0}},
        }
    ],
    "edges": [],
}


def test_plan_endpoint_returns_400_without_api_key(tmp_path: Path, monkeypatch) -> None:
    from translip.server.app import app
    from translip.server.routes import assistant as assistant_route

    def _raise(*args, **kwargs):
        raise BackendUnavailableError("未配置 DeepSeek API Key")

    monkeypatch.setattr(assistant_route, "generate_plan", _raise)
    client = TestClient(app)
    resp = client.post("/api/assistant/plan", json={"message": "做点什么", "file_ids": []})
    assert resp.status_code == 400
    assert "DeepSeek" in resp.json()["detail"]


def test_plan_endpoint_returns_plan(tmp_path: Path, monkeypatch) -> None:
    from translip.server.app import app
    from translip.server.assistant.models import AssistantPlan, PlanResult
    from translip.server.routes import assistant as assistant_route

    monkeypatch.setattr(
        assistant_route,
        "generate_plan",
        lambda *a, **k: PlanResult(type="plan", plan=AssistantPlan.model_validate(_PLAN_PAYLOAD)),
    )
    client = TestClient(app)
    resp = client.post("/api/assistant/plan", json={"message": "探测这个文件"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == "plan"
    assert body["plan"]["steps"][0]["tool_id"] == "probe"


def test_plan_endpoint_returns_clarification(tmp_path: Path, monkeypatch) -> None:
    from translip.server.app import app
    from translip.server.assistant.models import Clarification, PlanResult
    from translip.server.routes import assistant as assistant_route

    monkeypatch.setattr(
        assistant_route,
        "generate_plan",
        lambda *a, **k: PlanResult(
            type="clarification",
            clarification=Clarification(question="你想翻译成哪种语言？", options=["中文", "英文"]),
        ),
    )
    client = TestClient(app)
    resp = client.post("/api/assistant/plan", json={"message": "翻译这个视频"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == "clarification"
    assert body["clarification"]["question"] == "你想翻译成哪种语言？"
    assert body["clarification"]["options"] == ["中文", "英文"]


def test_plan_endpoint_forwards_history_and_available_files(tmp_path: Path, monkeypatch) -> None:
    from translip.server.app import app
    from translip.server.assistant.models import AssistantPlan, PlanResult
    from translip.server.routes import assistant as assistant_route

    captured: dict = {}

    def _capture(message, **kwargs):
        captured["message"] = message
        captured.update(kwargs)
        return PlanResult(type="plan", plan=AssistantPlan.model_validate(_PLAN_PAYLOAD))

    monkeypatch.setattr(assistant_route, "generate_plan", _capture)
    client = TestClient(app)
    resp = client.post(
        "/api/assistant/plan",
        json={
            "message": "把刚才的人声配成英文",
            "history": [{"role": "user", "content": "提取这个视频的人声"}],
            "available_files": [{"label": "上一步产物：voice.wav", "filename": "voice.wav"}],
        },
    )
    assert resp.status_code == 200
    assert [t.role for t in captured["history"]] == ["user"]
    assert captured["available_files"][0].filename == "voice.wav"


def test_execute_and_poll_run(tmp_path: Path, monkeypatch) -> None:
    from translip.server.app import app
    from translip.server.assistant.executor import AssistantRunManager
    from translip.server.atomic_tools.job_manager import JobManager
    from translip.server.routes import assistant as assistant_route

    engine = _isolated_engine(tmp_path)
    manager = JobManager(root=tmp_path / "atomic-tools", db_engine=engine)
    manager.register_adapter("probe", StubProbe())
    runner = AssistantRunManager(job_manager=manager, db_engine=engine)
    monkeypatch.setattr(assistant_route, "run_manager", runner)
    # the atomic upload endpoint must hit the same isolated manager
    from translip.server.routes import atomic_tools as atomic_tools_route

    monkeypatch.setattr(atomic_tools_route, "job_manager", manager)

    client = TestClient(app)
    upload = client.post(
        "/api/atomic-tools/upload",
        files={"file": ("clip.mp4", BytesIO(b"video"), "video/mp4")},
    )
    file_id = upload.json()["file_id"]

    execute = client.post(
        "/api/assistant/execute",
        json={"plan": _PLAN_PAYLOAD, "file_ids": [file_id]},
    )
    assert execute.status_code == 200
    run_id = execute.json()["run_id"]

    final = None
    for _ in range(50):
        state = client.get(f"/api/assistant/runs/{run_id}").json()
        if state["status"] in ("completed", "failed", "cancelled"):
            final = state
            break
        time.sleep(0.1)
    assert final is not None, "run did not finish in time"
    assert final["status"] == "completed"
    assert final["steps"][0]["status"] == "completed"
    assert any(a["filename"] == "probe.json" for a in final["steps"][0]["artifacts"])


def test_run_not_found_returns_404(monkeypatch) -> None:
    from translip.server.app import app

    client = TestClient(app)
    resp = client.get("/api/assistant/runs/does-not-exist")
    assert resp.status_code == 404
