from __future__ import annotations

import asyncio
import io
from pathlib import Path

import pytest
from fastapi import UploadFile
from sqlmodel import SQLModel, create_engine

from translip.server.assistant.executor import AssistantRunManager
from translip.server.assistant.models import AssistantPlan, Binding, PlanStep
from translip.server.atomic_tools.job_manager import JobManager


def _isolated_engine(tmp_path: Path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'assistant-test.db'}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    return engine


class StubSeparation:
    def validate_params(self, params: dict) -> dict:
        return dict(params)

    def run(self, params: dict, input_dir: Path, output_dir: Path, on_progress) -> dict:
        on_progress(50.0, "separating")
        (output_dir / "voice.wav").write_bytes(b"VOICE")
        (output_dir / "background.wav").write_bytes(b"BG")
        return {"voice_file": "voice.wav", "background_file": "background.wav"}


class StubMixing:
    def __init__(self) -> None:
        self.seen: dict[str, bytes] = {}

    def validate_params(self, params: dict) -> dict:
        return dict(params)

    def run(self, params: dict, input_dir: Path, output_dir: Path, on_progress) -> dict:
        voice = next((input_dir / "voice_file").rglob("*"))
        background = next((input_dir / "background_file").rglob("*"))
        self.seen["voice"] = voice.read_bytes()
        self.seen["background"] = background.read_bytes()
        (output_dir / "mixed.wav").write_bytes(b"MIX")
        return {"mixed_file": "mixed.wav"}


def _wire(tmp_path: Path):
    engine = _isolated_engine(tmp_path)
    manager = JobManager(root=tmp_path / "atomic-tools", db_engine=engine)
    mixing = StubMixing()
    manager.register_adapter("separation", StubSeparation())
    manager.register_adapter("mixing", mixing)
    runner = AssistantRunManager(job_manager=manager, db_engine=engine)
    return manager, mixing, runner


def _two_step_plan() -> AssistantPlan:
    return AssistantPlan(
        summary="分离人声后混音",
        steps=[
            PlanStep(
                id="sep",
                tool_id="separation",
                title="人声分离",
                inputs={"file_id": Binding(source="upload", upload_index=0)},
            ),
            PlanStep(
                id="mix",
                tool_id="mixing",
                title="混音",
                inputs={
                    "voice_file_id": Binding(source="step", step_id="sep", output="voice_file"),
                    "background_file_id": Binding(
                        source="step", step_id="sep", output="background_file"
                    ),
                },
            ),
        ],
    )


def test_executor_chains_artifact_file_ids_between_steps(tmp_path: Path) -> None:
    manager, mixing, runner = _wire(tmp_path)
    upload = asyncio.run(
        manager.save_upload(
            UploadFile(
                filename="clip.wav",
                file=io.BytesIO(b"raw audio"),
                headers={"content-type": "audio/wav"},
            )
        )
    )

    run_id = runner.start_run(
        _two_step_plan(), upload_file_ids=[upload.file_id], background=False
    )
    state = runner.get_run(run_id)

    assert state.status == "completed"
    assert [s.status for s in state.steps] == ["completed", "completed"]
    # Step 2 received exactly the artifacts step 1 produced — proving file_id chaining.
    assert mixing.seen["voice"] == b"VOICE"
    assert mixing.seen["background"] == b"BG"
    mix_step = next(s for s in state.steps if s.id == "mix")
    assert any(a.filename == "mixed.wav" for a in mix_step.artifacts)


def test_executor_fails_run_when_a_step_fails(tmp_path: Path) -> None:
    engine = _isolated_engine(tmp_path)
    manager = JobManager(root=tmp_path / "atomic-tools", db_engine=engine)

    class Boom:
        def validate_params(self, params: dict) -> dict:
            return dict(params)

        def run(self, params, input_dir, output_dir, on_progress):
            raise RuntimeError("kaboom")

    manager.register_adapter("separation", Boom())
    runner = AssistantRunManager(job_manager=manager, db_engine=engine)
    upload = asyncio.run(
        manager.save_upload(
            UploadFile(
                filename="clip.wav",
                file=io.BytesIO(b"x"),
                headers={"content-type": "audio/wav"},
            )
        )
    )
    plan = AssistantPlan(
        steps=[
            PlanStep(
                id="sep",
                tool_id="separation",
                inputs={"file_id": Binding(source="upload", upload_index=0)},
            )
        ]
    )
    run_id = runner.start_run(plan, upload_file_ids=[upload.file_id], background=False)
    state = runner.get_run(run_id)
    assert state.status == "failed"
    assert state.steps[0].status == "failed"
    assert "kaboom" in (state.error_message or "")


def _seed_completed_run(tmp_path: Path):
    manager, mixing, runner = _wire(tmp_path)
    upload = asyncio.run(
        manager.save_upload(
            UploadFile(
                filename="clip.wav",
                file=io.BytesIO(b"raw audio"),
                headers={"content-type": "audio/wav"},
            )
        )
    )
    run_id = runner.start_run(
        _two_step_plan(), upload_file_ids=[upload.file_id], background=False
    )
    return runner, run_id


def test_list_runs_summarizes_chain(tmp_path: Path) -> None:
    runner, run_id = _seed_completed_run(tmp_path)
    listing = runner.list_runs()
    assert listing.total == 1
    item = listing.items[0]
    assert item.run_id == run_id
    assert item.status == "completed"
    assert (item.completed_steps, item.step_count) == (2, 2)
    assert item.tools == ["separation", "mixing"]
    assert item.elapsed_sec is not None


def test_list_runs_filters_by_status(tmp_path: Path) -> None:
    runner, _ = _seed_completed_run(tmp_path)
    assert runner.list_runs(status="completed").total == 1
    assert runner.list_runs(status="failed").total == 0


def test_delete_run_removes_record(tmp_path: Path) -> None:
    runner, run_id = _seed_completed_run(tmp_path)
    runner.delete_run(run_id)
    assert runner.list_runs().total == 0
    with pytest.raises(KeyError):
        runner.get_run(run_id)


def test_rerun_run_creates_a_new_record(tmp_path: Path) -> None:
    runner, run_id = _seed_completed_run(tmp_path)
    new_id = runner.rerun_run(run_id)
    assert new_id != run_id
    # start_run writes the new row synchronously before the worker thread starts.
    assert runner.list_runs().total == 2


def test_get_run_includes_plan_for_detail(tmp_path: Path) -> None:
    runner, run_id = _seed_completed_run(tmp_path)
    state = runner.get_run(run_id)
    assert state.plan is not None
    assert [s.tool_id for s in state.plan.steps] == ["separation", "mixing"]


def test_executor_errors_when_upload_missing(tmp_path: Path) -> None:
    _, _, runner = _wire(tmp_path)
    plan = AssistantPlan(
        steps=[
            PlanStep(
                id="sep",
                tool_id="separation",
                inputs={"file_id": Binding(source="upload", upload_index=0)},
            )
        ]
    )
    run_id = runner.start_run(plan, upload_file_ids=[], background=False)
    state = runner.get_run(run_id)
    assert state.status == "failed"
    assert "上传文件" in (state.error_message or "")
