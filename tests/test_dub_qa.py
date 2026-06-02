from __future__ import annotations

import json
from pathlib import Path

import pytest

from translip.quality import DubQaRequest, build_dub_qa
from translip.quality import translation_judge as tj_module
from translip.quality.dub_benchmark import DubBenchmarkRequest, build_dub_benchmark
from translip.quality.translation_judge import build_translation_judge


def _write(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _make_pipeline(root: Path) -> None:
    """Lay out a minimal task-c / task-d / task-e fixture for one input."""
    tc = root / "task-c" / "voice" / "clip"
    _write(
        tc / "translation.en.json",
        {
            "segments": [
                {"segment_id": "s1", "speaker_label": "SPK1", "start": 0.0, "end": 2.0,
                 "source_text": "你好世界", "target_text": "Hello world"},
                {"segment_id": "s2", "speaker_label": "SPK2", "start": 2.0, "end": 5.0,
                 "source_text": "我们一起去看电影吧", "target_text": "Let us go watch a movie together"},
                {"segment_id": "s3", "speaker_label": "SPK1", "start": 5.0, "end": 7.0,
                 "source_text": "这翻译有问题", "target_text": "banana airplane"},
                {"segment_id": "s4", "speaker_label": "SPK2", "start": 7.0, "end": 9.0,
                 "source_text": "漏掉的一句话在这里", "target_text": "This whole sentence is here"},
                # Translated but its speaker was never synthesized → must surface as undubbed.
                {"segment_id": "s6", "speaker_label": "SPK3", "start": 11.0, "end": 13.0,
                 "source_text": "这个说话人没被合成", "target_text": "This speaker was dropped"},
            ]
        },
    )
    td = root / "task-d" / "voice" / "clip"
    td_report = _write(
        td / "dub_report.en.json",
        {
            "segments": [
                {"segment_id": "s1", "backread_text": "hello world"},
                {"segment_id": "s2", "backread_text": "let us go watch a movie together"},
                {"segment_id": "s3", "backread_text": "banana airplane"},
                {"segment_id": "s4", "backread_text": "this"},  # heavy dropout
            ]
        },
    )

    def placed(seg_id, **over):
        base = {
            "segment_id": seg_id,
            "task_d_report_path": str(td_report),
            "audio_path": str(td / f"{seg_id}.wav"),
            "mix_status": "placed",
            "overall_status": "passed",
            "speaker_status": "passed",
            "intelligibility_status": "passed",
            "duration_status": "passed",
            "speaker_similarity": 0.7,
            "text_similarity": 0.95,
            "source_duration_sec": 2.0,
            "generated_duration_sec": 2.0,
            "subtitle_coverage_ratio": 0.9,
            "qa_flags": [],
        }
        base.update(over)
        return base

    mix = {
        "input": {
            "translation_path": str(tc / "translation.en.json"),
            "task_d_report_paths": [str(td_report)],
        },
        "stats": {
            "placed_count": 4,
            "skipped_count": 1,
            "skip_reason_counts": {"skipped_missing_audio": 1},
            "quality_summary": {
                "total_count": 5,
                "overall_status_counts": {"passed": 2, "failed": 1, "review": 1},
                "speaker_status_counts": {"failed": 1},
                "intelligibility_status_counts": {"failed": 0},
            },
            "audible_coverage": {"failed_count": 1, "failed_segment_ids": ["s2"]},
        },
        "placed_segments": [
            placed("s1", anchor_start=0.0, anchor_end=2.0, target_text="Hello world"),
            placed("s2", anchor_start=2.0, anchor_end=5.0, target_text="Let us go watch a movie together",
                   overall_status="failed", speaker_status="failed", duration_status="failed",
                   speaker_similarity=0.1, generated_duration_sec=6.0, source_duration_sec=3.0,
                   subtitle_coverage_ratio=0.4, qa_flags=["duration_may_overrun"]),
            placed("s3", anchor_start=5.0, anchor_end=7.0, target_text="banana airplane"),
            placed("s4", anchor_start=7.0, anchor_end=9.0, target_text="This whole sentence is here",
                   overall_status="review", intelligibility_status="review", text_similarity=0.5),
        ],
        "skipped_segments": [
            {"segment_id": "s5", "anchor_start": 9.0, "anchor_end": 11.0,
             "target_text": "Missing dub line", "mix_status": "skipped_missing_audio",
             "task_d_report_path": str(td_report)},
        ],
    }
    _write(root / "task-e" / "voice" / "mix_report.en.json", mix)


def test_dub_qa_join_and_issue_tags(tmp_path: Path):
    root = tmp_path / "pipeline"
    _make_pipeline(root)
    # Provide judge scores out of band (no API call) flagging s3.
    _write(
        root / "task-e" / "voice" / "judge_scores.en.json",
        {"scores": [
            {"segment_id": "s1", "score": 5.0, "adequacy": 5, "fluency": 5, "reason": "ok"},
            {"segment_id": "s3", "score": 1.2, "adequacy": 1, "fluency": 2, "reason": "wrong meaning"},
        ]},
    )
    result = build_dub_qa(
        DubQaRequest(
            pipeline_root=root,
            output_dir=tmp_path / "analysis",
            target_lang="en",
            judge_path=root / "task-e" / "voice" / "judge_scores.en.json",
        )
    )
    rows = {row["segment_id"]: row for row in result.report["segments"]}

    # Join pulled source text + backread + relative dub audio path.
    assert rows["s1"]["source_text"] == "你好世界"
    assert rows["s1"]["backread_text"] == "hello world"
    assert rows["s1"]["dub_audio_path"] == "task-d/voice/clip/s1.wav"
    assert rows["s1"]["issue_tags"] == []

    # Each pain point maps to the right tag.
    assert "timbre_mismatch" in rows["s2"]["issue_tags"]
    assert "pacing" in rows["s2"]["issue_tags"]
    assert "inaudible" in rows["s2"]["issue_tags"]
    assert "bad_translation" in rows["s3"]["issue_tags"]
    assert "dropout" in rows["s4"]["issue_tags"]
    assert rows["s4"]["dropout_ratio"] >= 0.34
    assert rows["s5"]["issue_tags"] == ["undubbed"]
    assert rows["s5"]["severity"] == "P0"
    assert rows["s5"]["placed"] is False

    # s6 was translated but never synthesized → undubbed via the translation universe.
    assert "s6" in rows
    assert rows["s6"]["mix_status"] == "not_synthesized"
    assert rows["s6"]["issue_tags"] == ["undubbed"]
    assert rows["s6"]["source_text"] == "这个说话人没被合成"

    summary = result.report["qa_summary"]
    assert summary["issue_counts"]["undubbed"] == 2  # s5 (skipped) + s6 (not synthesized)
    assert summary["coverage"] == {
        "translated_count": 6,
        "dubbed_count": 4,
        "undubbed_count": 2,
        "coverage_ratio": round(4 / 6, 4),
    }
    assert summary["problem_segment_count"] == 5
    assert summary["translation_judge"]["failed_count"] == 1

    # Artifacts written.
    assert result.artifacts.report_path.exists()
    assert result.artifacts.markdown_path.exists()
    assert result.artifacts.manifest_path.exists()


def test_benchmark_surfaces_undubbed(tmp_path: Path):
    root = tmp_path / "pipeline"
    _make_pipeline(root)
    result = build_dub_benchmark(
        DubBenchmarkRequest(pipeline_root=root, output_dir=tmp_path / "bench", target_lang="en")
    )
    metrics = result.benchmark["metrics"]
    assert metrics["undubbed_count"] == 1
    assert metrics["undubbed_ratio"] == 0.2
    assert metrics["skip_reason_counts"] == {"skipped_missing_audio": 1}
    gate = next(g for g in result.benchmark["gates"] if g["id"] == "undubbed_coverage")
    assert gate["status"] == "failed"


def test_dub_qa_pacing_subtypes_and_timbre_review(tmp_path: Path):
    """Post-fit fields split the old single 'pacing' tag and light up the timbre review band."""
    root = tmp_path / "pipeline"
    tc = root / "task-c" / "voice" / "clip"
    _write(
        tc / "translation.en.json",
        {"segments": [
            {"segment_id": f"p{i}", "speaker_label": "SPK1", "start": float(i * 2), "end": float(i * 2 + 2),
             "source_text": "源句", "target_text": "target text here"}
            for i in range(1, 5)
        ]},
    )
    td = root / "task-d" / "voice" / "clip"
    td_report = _write(
        td / "dub_report.en.json",
        {"segments": [{"segment_id": f"p{i}", "backread_text": "target text here"} for i in range(1, 5)]},
    )

    def placed(seg_id, **over):
        base = {
            "segment_id": seg_id, "task_d_report_path": str(td_report),
            "audio_path": str(td / f"{seg_id}.wav"), "mix_status": "placed",
            "overall_status": "passed", "speaker_status": "passed", "intelligibility_status": "passed",
            "duration_status": "passed", "speaker_similarity": 0.7, "text_similarity": 0.95,
            "source_duration_sec": 2.0, "generated_duration_sec": 2.0,
            "subtitle_coverage_ratio": 0.9, "qa_flags": [],
            "applied_tempo": 1.0, "trimmed_tail_sec": 0.0, "dead_air_sec": 0.0, "placed_duration_ratio": 1.0,
        }
        base.update(over)
        return base

    mix = {
        "input": {"translation_path": str(tc / "translation.en.json"), "task_d_report_paths": [str(td_report)]},
        "stats": {
            "placed_count": 4, "skipped_count": 0, "skip_reason_counts": {},
            "quality_summary": {
                "total_count": 4, "overall_status_counts": {"passed": 4},
                "speaker_status_counts": {"passed": 3, "review": 1},
                "intelligibility_status_counts": {"passed": 4},
                "medians": {"speaker_similarity": 0.40},
            },
            "audible_coverage": {"failed_count": 0, "failed_segment_ids": []},
        },
        "placed_segments": [
            placed("p1", trimmed_tail_sec=0.8, applied_tempo=1.45, placed_duration_ratio=1.28),  # tail cut off
            placed("p2", applied_tempo=1.45),  # over-compressed, no trim
            placed("p3", dead_air_sec=1.2, placed_duration_ratio=0.4, generated_duration_sec=0.8),  # dead air
            placed("p4", speaker_status="review", speaker_similarity=0.33),  # timbre review band
        ],
        "skipped_segments": [],
    }
    _write(root / "task-e" / "voice" / "mix_report.en.json", mix)

    result = build_dub_qa(DubQaRequest(pipeline_root=root, output_dir=tmp_path / "analysis", target_lang="en"))
    rows = {row["segment_id"]: row for row in result.report["segments"]}

    assert "cutoff" in rows["p1"]["issue_tags"]
    assert "overcompressed" not in rows["p1"]["issue_tags"]  # cut-off takes precedence over rushed
    assert rows["p1"]["severity"] == "P1"
    assert rows["p1"]["trimmed_tail_sec"] == 0.8
    assert "overcompressed" in rows["p2"]["issue_tags"]
    assert "deadair" in rows["p3"]["issue_tags"]
    assert rows["p4"]["issue_tags"] == ["timbre_review"]

    counts = result.report["qa_summary"]["issue_counts"]
    assert (counts["cutoff"], counts["overcompressed"], counts["deadair"], counts["timbre_review"]) == (1, 1, 1, 1)


def test_dub_qa_flags_buried_dub(tmp_path: Path):
    """A placed segment whose dub sits below the SNR floor is inaudible → blocked."""
    root = tmp_path / "pipeline"
    tc = root / "task-c" / "voice" / "clip"
    _write(
        tc / "translation.en.json",
        {"segments": [{"segment_id": "b1", "speaker_label": "S", "start": 0.0, "end": 2.0,
                       "source_text": "源句", "target_text": "hello there"}]},
    )
    td = root / "task-d" / "voice" / "clip"
    tdr = _write(td / "dub_report.en.json", {"segments": [{"segment_id": "b1", "backread_text": "hello there"}]})
    mix = {
        "input": {"translation_path": str(tc / "translation.en.json"), "task_d_report_paths": [str(tdr)]},
        "stats": {
            "placed_count": 1, "skipped_count": 0, "skip_reason_counts": {},
            "quality_summary": {
                "total_count": 1, "overall_status_counts": {"passed": 1},
                "speaker_status_counts": {"passed": 1}, "intelligibility_status_counts": {"passed": 1},
            },
            "audible_coverage": {"failed_count": 0, "failed_segment_ids": []},
        },
        "placed_segments": [{
            "segment_id": "b1", "task_d_report_path": str(tdr), "audio_path": str(td / "b1.wav"),
            "mix_status": "placed", "overall_status": "passed", "speaker_status": "passed",
            "intelligibility_status": "passed", "duration_status": "passed",
            "speaker_similarity": 0.7, "text_similarity": 0.95, "source_duration_sec": 2.0,
            "generated_duration_sec": 2.0, "applied_tempo": 1.0, "trimmed_tail_sec": 0.0,
            "dead_air_sec": 0.0, "placed_duration_ratio": 1.0, "subtitle_coverage_ratio": 0.9,
            "dub_snr_db": -4.0, "qa_flags": [],
        }],
        "skipped_segments": [],
    }
    _write(root / "task-e" / "voice" / "mix_report.en.json", mix)

    result = build_dub_qa(DubQaRequest(pipeline_root=root, output_dir=tmp_path / "analysis", target_lang="en"))
    row = result.report["segments"][0]
    assert "inaudible" in row["issue_tags"]
    assert row["dub_snr_db"] == -4.0
    sc = result.report["scorecard"]
    assert sc["metrics"]["buried_count"] == 1
    assert sc["status"] == "blocked"
    assert next(g for g in sc["gates"] if g["id"] == "audibility")["status"] == "failed"


def test_dub_qa_handles_missing_mix_report(tmp_path: Path):
    # No pipeline artifacts at all → empty but well-formed report.
    result = build_dub_qa(
        DubQaRequest(pipeline_root=tmp_path / "empty", output_dir=tmp_path / "out", target_lang="en")
    )
    assert result.report["segments"] == []
    assert result.report["qa_summary"]["segment_count"] == 0
    assert result.manifest["status"] == "succeeded"


def test_translation_judge_with_mocked_api(tmp_path: Path, monkeypatch):
    translation = _write(
        tmp_path / "translation.en.json",
        {"segments": [
            {"segment_id": "s1", "source_text": "你好", "target_text": "Hello"},
            {"segment_id": "s2", "source_text": "再见", "target_text": "banana"},
        ]},
    )

    def fake_post(*, url, api_key, payload, timeout_sec):
        return {"choices": [{"message": {"content": json.dumps({"segments": [
            {"segment_id": "s1", "adequacy": 5, "fluency": 5, "reason": "ok"},
            {"segment_id": "s2", "adequacy": 1, "fluency": 2, "reason": "wrong word"},
        ]})}}]}

    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr(tj_module, "post_chat_completion", fake_post)

    out_path = build_translation_judge(
        translation_path=translation,
        output_dir=tmp_path / "judge",
        target_lang="en",
        source_lang="zh",
    )
    assert out_path is not None
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    scores = {row["segment_id"]: row for row in payload["scores"]}
    assert scores["s1"]["score"] == pytest.approx(5.0)
    assert scores["s2"]["score"] < 3.0  # weighted (1*0.6 + 2*0.4) = 1.4
    assert payload["stats"]["failed_count"] == 1


def test_translation_judge_missing_key_raises(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    translation = _write(
        tmp_path / "translation.en.json",
        {"segments": [{"segment_id": "s1", "source_text": "你好", "target_text": "Hello"}]},
    )
    from translip.exceptions import BackendUnavailableError

    with pytest.raises(BackendUnavailableError):
        build_translation_judge(
            translation_path=translation,
            output_dir=tmp_path / "judge",
            target_lang="en",
        )
