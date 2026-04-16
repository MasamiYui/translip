from __future__ import annotations

from datetime import datetime
from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine, select

from translip.server.models import Task, TaskStage
from translip.server.schemas import CreateTaskRequest, RerunTaskRequest, TaskConfigInput


def test_normalize_task_storage_splits_legacy_flat_config() -> None:
    from translip.server.task_config import (
        normalize_task_config,
        normalize_task_delivery_config,
        normalize_task_storage,
    )

    storage = normalize_task_storage(
        {
            "template": "asr-dub+ocr-subs+erase",
            "run_to_stage": "task-e",
            "video_source": "original",
            "audio_source": "both",
            "subtitle_source": "asr",
            "subtitle_mode": "bilingual",
            "subtitle_render_source": "asr",
            "subtitle_font": "Source Han Sans",
        }
    )

    assert storage["pipeline"]["template"] == "asr-dub+ocr-subs+erase"
    assert storage["pipeline"]["run_to_stage"] == "task-g"
    assert storage["pipeline"]["video_source"] == "clean_if_available"
    assert storage["pipeline"]["audio_source"] == "both"
    assert storage["delivery"]["subtitle_mode"] == "bilingual"
    assert storage["delivery"]["subtitle_render_source"] == "asr"
    assert storage["delivery"]["subtitle_font"] == "Source Han Sans"
    assert normalize_task_config(storage) == storage["pipeline"]
    assert normalize_task_delivery_config(storage) == storage["delivery"]


def test_build_pipeline_request_upgrades_legacy_erase_defaults(tmp_path: Path) -> None:
    from translip.server.task_manager import _build_pipeline_request

    task = Task(
      id="task-legacy-config",
      name="Legacy Config",
      status="pending",
      input_path=str(tmp_path / "input.mp4"),
      output_root=str(tmp_path / "output"),
      source_lang="zh",
      target_lang="en",
      config={
          "pipeline": {
              "template": "asr-dub+ocr-subs+erase",
              "run_to_stage": "task-e",
              "video_source": "original",
              "audio_source": "both",
              "subtitle_source": "asr",
          },
          "delivery": {
              "subtitle_mode": "english_only",
              "subtitle_render_source": "asr",
              "subtitle_font": "Source Han Sans",
              "subtitle_position": "top",
          },
      },
      created_at=datetime.now(),
      updated_at=datetime.now(),
    )

    request = _build_pipeline_request(task)

    assert request.run_to_stage == "task-g"
    assert request.delivery_policy["video_source"] == "clean_if_available"
    assert request.subtitle_mode == "english_only"
    assert request.subtitle_source == "asr"
    assert request.subtitle_style is not None
    assert request.subtitle_style.font_family == "Source Han Sans"
    assert request.subtitle_style.position == "top"


def test_task_manager_create_task_normalizes_legacy_erase_defaults(
    tmp_path: Path, monkeypatch
) -> None:
    from translip.server.task_manager import TaskManager
    import translip.server.task_manager as task_manager_module

    class DummyThread:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        def start(self) -> None:
            return None

    monkeypatch.setattr(task_manager_module.threading, "Thread", DummyThread)

    engine = create_engine(
        f"sqlite:///{tmp_path / 'tasks.db'}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)

    request = CreateTaskRequest(
        name="Legacy Frontend Task",
        input_path=str(tmp_path / "input.mp4"),
        source_lang="zh",
        target_lang="en",
        config=TaskConfigInput(
            template="asr-dub+ocr-subs+erase",
            run_to_stage="task-e",
            video_source="original",
            audio_source="both",
            subtitle_source="asr",
        ),
    )

    with Session(engine) as session:
        task = TaskManager().create_task(session, request)
        session.refresh(task)
        stage_names = [
            row.stage_name
            for row in session.exec(
                select(TaskStage).where(TaskStage.task_id == task.id)
            ).all()
        ]

    assert task.config["pipeline"]["run_to_stage"] == "task-g"
    assert task.config["pipeline"]["video_source"] == "clean_if_available"
    assert task.config["delivery"]["subtitle_mode"] == "none"
    assert "subtitle-erase" in stage_names
    assert "task-g" in stage_names


def test_rerun_task_upgrades_legacy_erase_defaults(tmp_path: Path, monkeypatch) -> None:
    from translip.server.routes.tasks import rerun_task
    import translip.server.task_manager as task_manager_module

    class DummyThread:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        def start(self) -> None:
            return None

    monkeypatch.setattr(task_manager_module.threading, "Thread", DummyThread)

    engine = create_engine(
        f"sqlite:///{tmp_path / 'tasks.db'}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)

    original_id = "task-legacy-original"
    original = Task(
        id=original_id,
        name="Legacy Original",
        status="succeeded",
        input_path=str(tmp_path / "input.mp4"),
        output_root=str(tmp_path / "output"),
        source_lang="zh",
        target_lang="en",
        config={
            "template": "asr-dub+ocr-subs+erase",
            "run_to_stage": "task-e",
            "video_source": "original",
            "audio_source": "both",
            "subtitle_source": "asr",
            "subtitle_mode": "english_only",
        },
    )

    with Session(engine) as session:
        session.add(original)
        session.commit()
        rerun = rerun_task(
            original.id,
            RerunTaskRequest(from_stage="task-c"),
            session,
        )

    assert rerun.parent_task_id == original_id
    assert rerun.config["run_from_stage"] == "task-c"
    assert rerun.config["run_to_stage"] == "task-g"
    assert rerun.config["video_source"] == "clean_if_available"
    assert rerun.delivery_config["subtitle_mode"] == "english_only"
    assert "task-g" in [stage.stage_name for stage in rerun.stages]
