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
    """Lay out a minimal translation / synthesis / render fixture for one input."""
    tc = root / "translation" / "voice" / "clip"
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
    td = root / "synthesis" / "voice" / "clip"
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
    _write(root / "render" / "voice" / "mix_report.en.json", mix)


def test_dub_qa_join_and_issue_tags(tmp_path: Path):
    root = tmp_path / "pipeline"
    _make_pipeline(root)
    # Provide judge scores out of band (no API call) flagging s3.
    _write(
        root / "render" / "voice" / "judge_scores.en.json",
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
            judge_path=root / "render" / "voice" / "judge_scores.en.json",
        )
    )
    rows = {row["segment_id"]: row for row in result.report["segments"]}

    # Join pulled source text + backread + relative dub audio path.
    assert rows["s1"]["source_text"] == "你好世界"
    assert rows["s1"]["backread_text"] == "hello world"
    assert rows["s1"]["dub_audio_path"] == "synthesis/voice/clip/s1.wav"
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


def _overflow_pipeline(root: Path) -> None:
    """A pipeline where placed dubs overflow their windows to varying degrees."""
    tc = root / "translation" / "voice" / "clip"
    _write(tc / "translation.en.json", {"segments": [
        {"segment_id": "ok", "speaker_label": "A", "start": 0.0, "end": 3.0,
         "source_text": "正常", "target_text": "fine"},
        {"segment_id": "severe", "speaker_label": "A", "start": 3.0, "end": 6.0,
         "source_text": "稍微长一点点的句子", "target_text": "a sentence that runs a bit long"},
        {"segment_id": "cut", "speaker_label": "A", "start": 6.0, "end": 9.0,
         "source_text": "被切尾的句子", "target_text": "this one gets its tail cut"},
    ]})

    def placed(seg_id, **over):
        base = {
            "segment_id": seg_id, "audio_path": str(tc / f"{seg_id}.wav"), "mix_status": "placed",
            "overall_status": "passed", "speaker_status": "passed",
            "intelligibility_status": "passed", "duration_status": "passed",
            "speaker_similarity": 0.7, "text_similarity": 0.95,
            "source_duration_sec": 3.0, "generated_duration_sec": 3.0,
            "fitted_duration_sec": 3.0, "subtitle_coverage_ratio": 0.9, "qa_flags": [],
        }
        base.update(over)
        return base

    _write(root / "render" / "voice" / "mix_report.en.json", {
        "input": {"translation_path": str(tc / "translation.en.json")},
        "stats": {"placed_count": 3, "skipped_count": 0,
                  "quality_summary": {"total_count": 3, "overall_status_counts": {"passed": 3}}},
        "placed_segments": [
            placed("ok", anchor_start=0.0, anchor_end=3.0),
            # ratio 1.55 → in the [1.35,1.65] "review" band (NOT duration_status=failed),
            # but severe enough to trim → must be flagged pacing.
            placed("severe", anchor_start=3.0, anchor_end=6.0,
                   generated_duration_sec=4.65, fitted_duration_sec=3.0, duration_status="review"),
            # Couldn't fit at all → 2.0s of tail cut, but only 1.4s of it was
            # speech (0.6s was trailing silence), so the honest loss is 1.4s.
            placed("cut", anchor_start=6.0, anchor_end=9.0,
                   generated_duration_sec=5.0, fitted_duration_sec=3.0,
                   trimmed_tail_sec=2.0, trimmed_speech_sec=1.4,
                   fit_strategy="overflow_unfitted", duration_status="review"),
        ],
        "skipped_segments": [],
    })


def test_severe_overflow_is_flagged_pacing(tmp_path: Path):
    root = tmp_path / "pipeline"
    _overflow_pipeline(root)
    result = build_dub_qa(DubQaRequest(pipeline_root=root, output_dir=tmp_path / "out", target_lang="en"))
    rows = {row["segment_id"]: row for row in result.report["segments"]}

    assert rows["ok"]["issue_tags"] == []  # ratio 1.0 → clean
    # 1.55× overflow slips through duration_status as "review", but is trimmed →
    # flagged pacing so the remediation/auto-fix loop will target it.
    assert "pacing" in rows["severe"]["issue_tags"]
    assert "pacing" in rows["cut"]["issue_tags"]


def test_timeline_summary_quantifies_overflow_and_cut_audio(tmp_path: Path):
    root = tmp_path / "pipeline"
    _overflow_pipeline(root)
    result = build_dub_qa(DubQaRequest(pipeline_root=root, output_dir=tmp_path / "out", target_lang="en"))
    timeline = result.report["qa_summary"]["timeline"]

    assert timeline["overflow_segment_count"] == 2  # severe (1.55) + cut (1.67)
    assert timeline["severe_overflow_count"] == 2
    assert timeline["unfitted_count"] == 1
    # Only the unfitted segment lost audio: 5.0 generated - 3.0 fitted = 2.0s.
    assert timeline["cut_audio_sec"] == 2.0
    assert timeline["max_duration_ratio"] >= 1.66


def test_lost_speech_sec_excludes_trailing_silence_trims(tmp_path: Path):
    root = tmp_path / "pipeline"
    _overflow_pipeline(root)
    result = build_dub_qa(DubQaRequest(pipeline_root=root, output_dir=tmp_path / "out", target_lang="en"))
    timeline = result.report["qa_summary"]["timeline"]

    # cut_audio_sec (2.0) conflates time-stretch shrink + trim, over-reporting
    # loss. lost_speech_sec is the honest signal: of the 2.0s tail actually cut,
    # only 1.4s was speech — the 0.6s of trailing silence is not a dropped word.
    assert timeline["lost_speech_sec"] == 1.4
    assert timeline["lost_speech_sec"] < timeline["cut_audio_sec"]
    # The one trim dropped speech, so it is not a harmless silence-only trim.
    assert timeline["silence_only_trim_count"] == 0


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


def test_perceptual_score_penalizes_tail_cut_and_overflow() -> None:
    from translip.quality.dub_qa import _perceptual_score

    clean = _perceptual_score(
        timeline={"cut_audio_sec": 0.0, "severe_overflow_count": 0},
        undubbed_count=0,
        segment_count=180,
    )
    assert clean == 100.0

    # The documented 90.3-hygiene / 62.5s-cut run should look far worse perceptually.
    cut = _perceptual_score(
        timeline={"cut_audio_sec": 62.5, "severe_overflow_count": 45},
        undubbed_count=2,
        segment_count=180,
    )
    assert cut < clean
    assert cut <= 60.0

    # Monotonic: more audio cut never improves the score.
    more_cut = _perceptual_score(
        timeline={"cut_audio_sec": 90.0, "severe_overflow_count": 45},
        undubbed_count=2,
        segment_count=180,
    )
    assert more_cut <= cut

    assert _perceptual_score(timeline={}, undubbed_count=0, segment_count=0) == 100.0
