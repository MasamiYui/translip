from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from translip.server.app import app
from translip.server.database import get_session
from translip.server.models import Task


def test_dubbing_editor_import_reads_timeline_mix_report_and_character_ledger(tmp_path: Path) -> None:
    engine = _test_engine(tmp_path, "dubbing-editor.db")
    output_root = tmp_path / "output"
    _write_editor_fixture(output_root)

    with Session(engine) as session:
        session.add(_task(output_root))
        session.commit()

    def override_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        client = TestClient(app)
        response = client.get("/api/tasks/task-dubbing-editor/dubbing-editor")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()

    assert payload["summary"]["unit_count"] == 3
    assert payload["summary"]["issue_count"] == 5
    assert payload["summary"]["p0_count"] == 2
    assert payload["summary"]["char_review_count"] == 1

    first_unit = payload["units"][0]
    assert first_unit["current_clip"]["mix_status"] == "placed"
    assert first_unit["current_clip"]["audio_artifact_path"] == "task-e/.work/job-1/fit/seg-0001.wav"
    assert first_unit["current_clip"]["duration"] == 1.1

    failed_unit = payload["units"][1]
    assert failed_unit["status"] == "needs_review"
    assert set(failed_unit["issue_ids"]) == {
        "duration_fit_failed:seg-0002",
        "speaker_similarity_failed:seg-0002",
        "translation_untrusted:seg-0002",
        "silent_with_subtitle:seg-0002",
    }

    review_character = payload["characters"][0]
    assert review_character["review_status"] == "needs_review"
    assert review_character["risk_flags"] == ["speaker_similarity_failed"]
    assert review_character["stats"]["speaker_failed_ratio"] == 1.0
    assert review_character["pitch_class"] == "low"
    assert review_character["pitch_hz"] == 118.0


def _test_engine(tmp_path: Path, name: str):
    engine = create_engine(
        f"sqlite:///{tmp_path / name}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    return engine


def _task(output_root: Path) -> Task:
    return Task(
        id="task-dubbing-editor",
        name="Dubbing Editor",
        status="succeeded",
        input_path=str(output_root / "input.mp4"),
        output_root=str(output_root),
        source_lang="zh",
        target_lang="en",
        config={"pipeline": {"template": "asr-dub-basic"}},
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )


def _write_editor_fixture(output_root: Path) -> None:
    fitted_audio = output_root / "task-e" / ".work" / "job-1" / "fit" / "seg-0001.wav"
    source_audio = output_root / "task-d" / "voice" / "spk_0001" / "segments" / "seg-0002.wav"
    fitted_audio.parent.mkdir(parents=True, exist_ok=True)
    source_audio.parent.mkdir(parents=True, exist_ok=True)
    fitted_audio.write_bytes(b"fitted")
    source_audio.write_bytes(b"source")

    _write_json(
        output_root / "task-c" / "voice" / "translation.en.json",
        {
            "segments": [
                {
                    "segment_id": "seg-0001",
                    "speaker_id": "spk_0001",
                    "start": 1.0,
                    "end": 2.2,
                    "duration": 1.2,
                    "source_text": "第一句",
                    "target_text": "First line.",
                },
                {
                    "segment_id": "seg-0002",
                    "speaker_id": "spk_0001",
                    "start": 2.2,
                    "end": 3.0,
                    "duration": 0.8,
                    "source_text": "第二句",
                    "target_text": "Second line.",
                },
                {
                    "segment_id": "seg-0003",
                    "speaker_id": "spk_0002",
                    "start": 3.0,
                    "end": 4.0,
                    "duration": 1.0,
                    "source_text": "第三句",
                    "target_text": "Third line.",
                },
            ]
        },
    )
    _write_json(
        output_root / "task-e" / "voice" / "timeline.en.json",
        {
            "items": [
                {
                    "segment_id": "seg-0001",
                    "speaker_id": "spk_0001",
                    "fitted_duration_sec": 1.1,
                    "fit_strategy": "compress",
                    "mix_status": "placed",
                    "fitted_audio_path": str(fitted_audio),
                    "duration_status": "passed",
                    "speaker_status": "passed",
                    "intelligibility_status": "passed",
                    "overall_status": "passed",
                },
                {
                    "segment_id": "seg-0002",
                    "speaker_id": "spk_0001",
                    "fitted_duration_sec": 0.7,
                    "fit_strategy": "underflow_unfitted",
                    "mix_status": "placed",
                    "audio_path": str(source_audio),
                    "duration_status": "failed",
                    "speaker_status": "failed",
                    "intelligibility_status": "failed",
                    "overall_status": "failed",
                    "notes": ["task_d_failed_upstream"],
                },
                {
                    "segment_id": "seg-0003",
                    "speaker_id": "spk_0002",
                    "mix_status": "skipped_overlap",
                    "duration_status": "passed",
                    "speaker_status": "passed",
                    "intelligibility_status": "passed",
                    "overall_status": "review",
                    "notes": ["subtitle_window_not_rendered"],
                },
            ]
        },
    )
    _write_json(
        output_root / "task-e" / "voice" / "mix_report.en.json",
        {
            "placed_segments": [],
            "skipped_segments": [],
            "stats": {
                "quality_summary": {
                    "overall_status_counts": {"failed": 1, "passed": 1, "review": 1},
                    "speaker_status_counts": {"failed": 1, "passed": 2},
                    "intelligibility_status_counts": {"failed": 1, "passed": 2},
                }
            },
        },
    )
    _write_json(
        output_root / "task-d" / "voice" / "character-ledger" / "character_ledger.en.json",
        {
            "characters": [
                {
                    "character_id": "char_0001",
                    "display_name": "SPEAKER_01",
                    "speaker_ids": ["spk_0001"],
                    "voice_signature": {"pitch_hz": 118.0, "pitch_class": "low"},
                    "stats": {
                        "segment_count": 1,
                        "speaker_failed_count": 1,
                        "overall_failed_count": 1,
                        "voice_mismatch_count": 0,
                        "speaker_failed_ratio": 1.0,
                    },
                    "risk_flags": ["speaker_similarity_failed"],
                    "review_status": "review",
                },
                {
                    "character_id": "char_0002",
                    "display_name": "SPEAKER_02",
                    "speaker_ids": ["spk_0002"],
                    "voice_signature": {"pitch_hz": 210.0, "pitch_class": "mid"},
                    "stats": {
                        "segment_count": 1,
                        "speaker_failed_count": 0,
                        "overall_failed_count": 0,
                        "voice_mismatch_count": 0,
                        "speaker_failed_ratio": 0.0,
                    },
                    "risk_flags": [],
                    "review_status": "passed",
                },
            ]
        },
    )
    _write_json(
        output_root / "benchmark" / "voice" / "dub_benchmark.en.json",
        {
            "version": "dub-benchmark-v0",
            "status": "blocked",
            "score": 44.6,
            "reasons": ["audible_coverage_failed", "upstream_failed_segments"],
            "metrics": {
                "total_segment_count": 3,
                "audible_failed_count": 1,
                "audible_failed_segment_ids": ["seg-0002"],
                "overall_failed_count": 1,
                "speaker_failed_count": 1,
                "intelligibility_failed_count": 1,
                "character_review_count": 1,
            },
            "gates": [],
        },
    )


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
