from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlmodel import Session, SQLModel, create_engine, select

from translip.server.models import Task, TaskStage
from translip.server.schemas import CreateTaskRequest, RerunTaskRequest, TaskConfigInput


def test_task_config_validates_dubbing_speed_controls() -> None:
    config = TaskConfigInput(dubbing_workers=4, dubbing_quality_check="duration-only")

    assert config.dubbing_workers == 4
    assert config.dubbing_quality_check == "duration-only"

    with pytest.raises(ValidationError):
        TaskConfigInput(dubbing_workers=0)
    with pytest.raises(ValidationError):
        TaskConfigInput(dubbing_quality_check="fast")


def test_task_config_accepts_transcription_advanced_controls() -> None:
    config = TaskConfigInput(
        asr_backend="funasr",
        diarizer_backend="pyannote",
        enable_diarization=False,
        vad_filter=False,
        vad_min_silence_duration_ms=650,
        beam_size=3,
        best_of=2,
        temperature=0.2,
        condition_on_previous_text=True,
    )

    assert config.asr_backend == "funasr"
    assert config.diarizer_backend == "pyannote"
    assert config.enable_diarization is False
    assert config.vad_filter is False
    assert config.vad_min_silence_duration_ms == 650
    assert config.beam_size == 3
    assert config.best_of == 2
    assert config.temperature == 0.2
    assert config.condition_on_previous_text is True

    with pytest.raises(ValidationError):
        TaskConfigInput(vad_min_silence_duration_ms=0)
    with pytest.raises(ValidationError):
        TaskConfigInput(beam_size=0)
    with pytest.raises(ValidationError):
        TaskConfigInput(best_of=0)
    with pytest.raises(ValidationError):
        TaskConfigInput(temperature=-0.1)
    with pytest.raises(ValidationError):
        TaskConfigInput(asr_backend="unknown")
    with pytest.raises(ValidationError):
        TaskConfigInput(diarizer_backend="unknown")


def test_task_config_accepts_node_advanced_controls() -> None:
    config = TaskConfigInput(
        stage1_output_format="wav",
        audio_stream_index=1,
        top_k=4,
        translation_batch_size=8,
        deepseek_model="deepseek-v4-pro",
        dubbing_workers=2,
        dub_repair_enabled=True,
        dub_repair_max_items=6,
        dub_repair_attempts_per_item=2,
        fit_policy="high_quality",
        window_ducking_db=-4.0,
        max_compress_ratio=1.35,
        output_sample_rate=48000,
        preview_format="mp3",
    )

    assert config.stage1_output_format == "wav"
    assert config.audio_stream_index == 1
    assert config.top_k == 4
    assert config.translation_batch_size == 8
    assert config.deepseek_model == "deepseek-v4-pro"
    assert config.dubbing_workers == 2
    assert config.dub_repair_enabled is True
    assert config.dub_repair_max_items == 6
    assert config.dub_repair_attempts_per_item == 2
    assert config.fit_policy == "high_quality"
    assert config.window_ducking_db == -4.0
    assert config.max_compress_ratio == 1.35
    assert config.output_sample_rate == 48000
    assert config.preview_format == "mp3"

    with pytest.raises(ValidationError):
        TaskConfigInput(audio_stream_index=-1)
    with pytest.raises(ValidationError):
        TaskConfigInput(translation_batch_size=0)
    with pytest.raises(ValidationError):
        TaskConfigInput(dub_repair_max_items=0)
    with pytest.raises(ValidationError):
        TaskConfigInput(max_compress_ratio=0)


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


def test_transcription_correction_defaults_to_standard_for_pipeline_config() -> None:
    from translip.server.task_config import normalize_task_config

    config = normalize_task_config({"template": "asr-dub+ocr-subs"})

    assert config["transcription_correction"] == {
        "enabled": True,
        "preset": "standard",
        "ocr_only_policy": "report_only",
        "llm_arbitration": "off",
    }


def test_build_pipeline_request_maps_transcription_correction(tmp_path: Path) -> None:
    from translip.server.task_manager import _build_pipeline_request

    task = Task(
        id="task-correction-config",
        name="Correction Config",
        status="pending",
        input_path=str(tmp_path / "input.mp4"),
        output_root=str(tmp_path / "output"),
        source_lang="zh",
        target_lang="en",
        config={
            "pipeline": {
                "template": "asr-dub+ocr-subs",
                "transcription_correction": {
                    "enabled": False,
                    "preset": "conservative",
                    "ocr_only_policy": "report_only",
                    "llm_arbitration": "off",
                },
            }
        },
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )

    request = _build_pipeline_request(task)

    assert request.transcription_correction["enabled"] is False
    assert request.transcription_correction["preset"] == "conservative"


def test_build_pipeline_request_maps_transcription_advanced_controls(tmp_path: Path) -> None:
    from translip.server.task_manager import _build_pipeline_request

    task = Task(
        id="task-transcription-advanced",
        name="Transcription Advanced",
        status="pending",
        input_path=str(tmp_path / "input.mp4"),
        output_root=str(tmp_path / "output"),
        source_lang="zh",
        target_lang="en",
        config={
            "pipeline": {
                "asr_model": "medium",
                "asr_backend": "funasr",
                "diarizer_backend": "pyannote",
                "enable_diarization": False,
                "vad_filter": False,
                "vad_min_silence_duration_ms": 650,
                "beam_size": 3,
                "best_of": 2,
                "temperature": 0.2,
                "condition_on_previous_text": True,
            }
        },
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )

    request = _build_pipeline_request(task)

    assert request.asr_model == "medium"
    assert request.asr_backend == "funasr"
    assert request.diarizer_backend == "pyannote"
    assert request.enable_diarization is False
    assert request.vad_filter is False
    assert request.vad_min_silence_duration_ms == 650
    assert request.beam_size == 3
    assert request.best_of == 2
    assert request.temperature == 0.2
    assert request.condition_on_previous_text is True


def test_build_pipeline_request_maps_node_advanced_controls(tmp_path: Path) -> None:
    from translip.server.task_manager import _build_pipeline_request

    task = Task(
        id="task-node-advanced",
        name="Node Advanced",
        status="pending",
        input_path=str(tmp_path / "input.mp4"),
        output_root=str(tmp_path / "output"),
        source_lang="zh",
        target_lang="en",
        config={
            "pipeline": {
                "stage1_output_format": "wav",
                "audio_stream_index": 1,
                "top_k": 4,
                "translation_batch_size": 8,
                "deepseek_model": "deepseek-v4-pro",
                "dubbing_workers": 2,
                "dub_repair_enabled": True,
                "dub_repair_backend": ["moss-tts-nano-onnx", "qwen3tts"],
                "dub_repair_max_items": 6,
                "dub_repair_attempts_per_item": 2,
                "dub_repair_include_risk": True,
                "fit_policy": "high_quality",
                "fit_backend": "rubberband",
                "mix_profile": "enhanced",
                "ducking_mode": "sidechain",
                "background_gain_db": -10.0,
                "window_ducking_db": -4.0,
                "max_compress_ratio": 1.35,
                "output_sample_rate": 48000,
                "preview_format": "mp3",
            },
            "delivery": {
                "subtitle_mode": "bilingual",
                "subtitle_render_source": "asr",
            },
        },
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )

    request = _build_pipeline_request(task)

    assert request.stage1_output_format == "wav"
    assert request.audio_stream_index == 1
    assert request.top_k == 4
    assert request.translation_batch_size == 8
    assert request.api_model == "deepseek-v4-pro"
    assert request.dubbing_workers == 2
    assert request.dub_repair_enabled is True
    assert request.dub_repair_backends == ["moss-tts-nano-onnx", "qwen3tts"]
    assert request.dub_repair_max_items == 6
    assert request.dub_repair_attempts_per_item == 2
    assert request.dub_repair_include_risk is True
    assert request.fit_policy == "high_quality"
    assert request.fit_backend == "rubberband"
    assert request.mix_profile == "enhanced"
    assert request.ducking_mode == "sidechain"
    assert request.background_gain_db == -10.0
    assert request.window_ducking_db == -4.0
    assert request.max_compress_ratio == 1.35
    assert request.output_sample_rate == 48000
    assert request.preview_format == "mp3"
    assert request.subtitle_mode == "bilingual"
    assert request.subtitle_source == "asr"


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


def test_task_config_accepts_subtitle_erase_controls() -> None:
    config = TaskConfigInput(
        erase_backend="lama",
        erase_device="cpu",
        erase_max_load=30,
        erase_mask_dilate_x=20,
        erase_mask_dilate_y=14,
        erase_event_lead_frames=5,
        erase_event_trail_frames=12,
        erase_neighbor_stride=4,
        erase_reference_length=8,
    )

    assert config.erase_backend == "lama"
    assert config.erase_device == "cpu"
    assert config.erase_max_load == 30
    assert config.erase_mask_dilate_x == 20
    assert config.erase_mask_dilate_y == 14
    assert config.erase_event_lead_frames == 5
    assert config.erase_event_trail_frames == 12
    assert config.erase_neighbor_stride == 4
    assert config.erase_reference_length == 8

    # backend is constrained to the two pipeline-supported inpainters
    with pytest.raises(ValidationError):
        TaskConfigInput(erase_backend="opencv")
    with pytest.raises(ValidationError):
        TaskConfigInput(erase_device="gpu")
    # positive-only knobs
    with pytest.raises(ValidationError):
        TaskConfigInput(erase_max_load=0)
    with pytest.raises(ValidationError):
        TaskConfigInput(erase_neighbor_stride=0)
    with pytest.raises(ValidationError):
        TaskConfigInput(erase_reference_length=0)
    # non-negative knobs
    with pytest.raises(ValidationError):
        TaskConfigInput(erase_mask_dilate_x=-1)
    with pytest.raises(ValidationError):
        TaskConfigInput(erase_event_lead_frames=-1)


def test_build_pipeline_request_maps_subtitle_erase_controls(tmp_path: Path) -> None:
    from translip.server.task_manager import _build_pipeline_request

    task = Task(
        id="task-erase-config",
        name="Erase Config",
        status="pending",
        input_path=str(tmp_path / "input.mp4"),
        output_root=str(tmp_path / "output"),
        source_lang="zh",
        target_lang="en",
        config={
            "pipeline": {
                "template": "asr-dub+ocr-subs+erase",
                "erase_backend": "lama",
                "erase_device": "cpu",
                "erase_max_load": 30,
                "erase_mask_dilate_x": 20,
                "erase_mask_dilate_y": 14,
                "erase_event_lead_frames": 5,
                "erase_event_trail_frames": 12,
                "erase_neighbor_stride": 4,
                "erase_reference_length": 8,
            }
        },
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )

    request = _build_pipeline_request(task)

    assert request.erase_backend == "lama"
    assert request.erase_device == "cpu"
    assert request.erase_max_load == 30
    assert request.erase_mask_dilate_x == 20
    assert request.erase_mask_dilate_y == 14
    assert request.erase_event_lead_frames == 5
    assert request.erase_event_trail_frames == 12
    assert request.erase_neighbor_stride == 4
    assert request.erase_reference_length == 8
