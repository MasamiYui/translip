from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from translip.server.app import app
from translip.server.database import get_session
from translip.server.models import Task


def test_dubbing_review_route_aggregates_repair_assets(tmp_path: Path) -> None:
    engine = _test_engine(tmp_path, "dubbing-review.db")
    output_root = tmp_path / "output"
    _write_review_fixture(output_root)

    with Session(engine) as session:
        session.add(_task(output_root))
        session.commit()

    def override_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        client = TestClient(app)
        response = client.get("/api/tasks/task-dubbing-review/dubbing-review")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "available"
    assert payload["summary"]["speaker_count"] == 1
    assert payload["summary"]["repair_item_count"] == 1
    assert payload["summary"]["merge_candidate_count"] == 1
    assert payload["summary"]["quality_status"] == "review_required"
    assert payload["summary"]["quality_score"] == 88.0
    assert payload["summary"]["character_review_count"] == 1
    assert payload["quality_benchmark"]["status"] == "review_required"
    assert payload["characters"][0]["character_id"] == "char_0001"
    assert payload["speakers"][0]["speaker_id"] == "spk_0001"
    assert payload["speakers"][0]["candidates"][0]["artifact_path"] == "task-b/voice/reference_clips/profile_0001/clip_0001.wav"
    assert payload["repair_items"][0]["audio_artifact_path"] == "task-d/voice/spk_0001/segments/seg-0001.wav"


def test_dubbing_review_decision_route_writes_latest_decision(tmp_path: Path) -> None:
    engine = _test_engine(tmp_path, "dubbing-review-decision.db")
    output_root = tmp_path / "output"
    _write_review_fixture(output_root)

    with Session(engine) as session:
        session.add(_task(output_root))
        session.commit()

    def override_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        client = TestClient(app)
        response = client.post(
            "/api/tasks/task-dubbing-review/dubbing-review/decisions",
            json={
                "category": "reference",
                "item_id": "spk_0001",
                "decision": "use_reference",
                "speaker_id": "spk_0001",
                "reference_path": str(output_root / "task-b/voice/reference_clips/profile_0001/clip_0001.wav"),
                "payload": {"reference_id": "clip_0001"},
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["decision_count"] == 1

    decision_path = output_root / "task-d" / "voice" / "manual_reference_decisions.en.json"
    payload = json.loads(decision_path.read_text(encoding="utf-8"))
    assert payload["decision_count"] == 1
    assert payload["decisions"][0]["item_id"] == "spk_0001"
    assert payload["decisions"][0]["decision"] == "use_reference"


def _test_engine(tmp_path: Path, name: str):
    engine = create_engine(
        f"sqlite:///{tmp_path / name}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    return engine


def _task(output_root: Path) -> Task:
    return Task(
        id="task-dubbing-review",
        name="Dubbing Review",
        status="succeeded",
        input_path=str(output_root / "input.mp4"),
        output_root=str(output_root),
        source_lang="zh",
        target_lang="en",
        config={"pipeline": {"template": "asr-dub-basic"}},
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )


def _write_review_fixture(output_root: Path) -> None:
    reference_path = output_root / "task-b" / "voice" / "reference_clips" / "profile_0001" / "clip_0001.wav"
    segment_audio = output_root / "task-d" / "voice" / "spk_0001" / "segments" / "seg-0001.wav"
    reference_path.parent.mkdir(parents=True, exist_ok=True)
    segment_audio.parent.mkdir(parents=True, exist_ok=True)
    reference_path.write_bytes(b"reference")
    segment_audio.write_bytes(b"segment")

    _write_json(
        output_root / "task-b" / "voice" / "speaker_profiles.json",
        {
            "profiles": [
                {
                    "profile_id": "profile_0001",
                    "source_label": "SPEAKER_01",
                    "speaker_id": "spk_0001",
                    "status": "registered",
                    "total_speech_sec": 12.5,
                    "segment_count": 3,
                    "reference_clip_count": 1,
                    "reference_clips": [
                        {
                            "path": str(reference_path),
                            "duration": 8.2,
                            "text": "测试参考音频",
                            "rms": 0.08,
                        }
                    ],
                }
            ]
        },
    )
    _write_json(
        output_root / "task-c" / "voice" / "translation.en.json",
        {
            "segments": [
                {
                    "segment_id": "seg-0001",
                    "speaker_id": "spk_0001",
                    "start": 1.0,
                    "end": 1.6,
                    "duration": 0.6,
                    "source_text": "走吧",
                    "target_text": "Let's go.",
                },
                {
                    "segment_id": "seg-0002",
                    "speaker_id": "spk_0001",
                    "start": 1.6,
                    "end": 2.2,
                    "duration": 0.6,
                    "source_text": "快点",
                    "target_text": "Hurry.",
                },
            ]
        },
    )
    _write_json(
        output_root / "task-d" / "voice" / "repair-plan" / "repair_queue.en.json",
        {
            "target_lang": "en",
            "stats": {"repair_count": 1},
            "items": [
                {
                    "segment_id": "seg-0001",
                    "speaker_id": "spk_0001",
                    "source_text": "走吧",
                    "target_text": "Let's go.",
                    "anchor_start": 1.0,
                    "anchor_end": 1.6,
                    "source_duration_sec": 0.6,
                    "generated_duration_sec": 4.0,
                    "audio_path": str(segment_audio),
                    "reference_path": str(reference_path),
                    "strict_blocker": True,
                    "priority": "high",
                    "failure_reasons": ["duration_failed"],
                    "suggested_actions": ["merge_short_segments", "rewrite_for_dubbing"],
                    "metrics": {"duration_ratio": 6.6},
                }
            ],
        },
    )
    _write_json(
        output_root / "task-d" / "voice" / "repair-plan" / "reference_plan.en.json",
        {
            "target_lang": "en",
            "speakers": [
                {
                    "speaker_id": "spk_0001",
                    "current_reference_path": str(reference_path),
                    "recommended_reference_path": str(reference_path),
                    "speaker_failed_count": 1,
                    "repair_item_count": 1,
                    "candidates": [
                        {
                            "path": str(reference_path),
                            "profile_id": "profile_0001",
                            "duration_sec": 8.2,
                            "text": "测试参考音频",
                            "rms": 0.08,
                            "quality_score": 0.9,
                            "is_current": True,
                        }
                    ],
                }
            ],
        },
    )
    _write_json(
        output_root / "task-d" / "voice" / "character-ledger" / "character_ledger.en.json",
        {
            "target_lang": "en",
            "stats": {
                "character_count": 1,
                "review_count": 1,
                "blocked_count": 0,
                "voice_mismatch_count": 1,
            },
            "characters": [
                {
                    "character_id": "char_0001",
                    "display_name": "SPEAKER_01",
                    "speaker_ids": ["spk_0001"],
                    "voice_signature": {"pitch_class": "low", "pitch_hz": 110.0},
                    "stats": {"voice_mismatch_count": 1, "speaker_failed_ratio": 1.0},
                    "risk_flags": ["pitch_class_drift"],
                    "review_status": "review",
                }
            ],
        },
    )
    _write_json(
        output_root / "benchmark" / "voice" / "dub_benchmark.en.json",
        {
            "version": "dub-benchmark-v0",
            "status": "review_required",
            "score": 88.0,
            "reasons": ["character_voice_review_required"],
            "metrics": {
                "coverage_ratio": 1.0,
                "audible_failed_count": 0,
                "character_review_count": 1,
                "voice_mismatch_count": 1,
                "repair_manual_required_count": 0,
            },
            "gates": [
                {"id": "coverage", "status": "passed", "value": 1.0},
                {"id": "character_voice", "status": "review", "value": {"review_count": 1}},
            ],
        },
    )


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
