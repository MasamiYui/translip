"""Unit tests for the dub remediation/optimization plan builder."""

from __future__ import annotations

from translip.quality.remediation import (
    ACTION_FILL,
    ACTION_REFIT,
    ACTION_RESYNTH,
    ACTION_RETRANSLATE,
    ACTION_REWRITE,
    ACTION_SWITCH_VOICE,
    EX_RENDER,
    EX_REPAIR,
    EX_RERUN,
    build_remediation_plan,
)


def _seg(segment_id, issue_tags, severity="P1", **fields):
    base = {
        "segment_id": segment_id,
        "start": 0.0,
        "speaker_id": "spk_0000",
        "issue_tags": issue_tags,
        "severity": severity,
        "duration_ratio": None,
        "fit_strategy": None,
        "speaker_similarity": None,
        "text_similarity": None,
        "dropout_ratio": None,
        "subtitle_coverage_ratio": None,
        "judge_score": None,
    }
    base.update(fields)
    return base


def _report(segments, gates=None):
    return {
        "segments": segments,
        "scorecard": {"gates": gates or []},
    }


def test_clean_segment_yields_no_directive():
    plan = build_remediation_plan(_report([_seg("s1", [], severity="ok")]))
    assert plan["summary"]["problem_count"] == 0
    assert plan["segment_directives"] == {}
    assert plan["repair_directive"] is None


def test_defect_to_action_mapping():
    segments = [
        _seg("undub", ["undubbed"], severity="P0"),
        _seg("timbre", ["timbre_mismatch"], speaker_similarity=0.3),
        _seg("drop", ["dropout"], dropout_ratio=0.5),
        _seg("trans", ["bad_translation"], judge_score=2.0),
        # pacing that fitting could not absorb -> rewrite (shorten)
        _seg("pace_over", ["pacing"], severity="P2", duration_ratio=1.6, fit_strategy="overflow_unfitted"),
        # mild pacing -> refit
        _seg("pace_mild", ["pacing"], severity="P2", duration_ratio=1.1, fit_strategy="compress"),
    ]
    plan = build_remediation_plan(_report(segments))
    d = plan["segment_directives"]
    assert d["undub"]["primary_action"] == ACTION_FILL
    assert d["undub"]["executor"] == EX_RERUN
    assert d["undub"]["auto_fixable"] is False
    assert d["timbre"]["primary_action"] == ACTION_SWITCH_VOICE
    assert d["timbre"]["executor"] == EX_REPAIR
    assert d["timbre"]["auto_fixable"] is True
    assert d["drop"]["primary_action"] == ACTION_RESYNTH
    assert d["trans"]["primary_action"] == ACTION_RETRANSLATE
    assert d["pace_over"]["primary_action"] == ACTION_REWRITE
    assert d["pace_mild"]["primary_action"] == ACTION_REFIT
    assert d["pace_mild"]["executor"] == EX_RENDER
    assert d["pace_mild"]["knob"] is not None


def test_repair_directive_collects_auto_fixable_only():
    segments = [
        _seg("undub", ["undubbed"], severity="P0"),  # not repair-driven
        _seg("timbre", ["timbre_mismatch"]),         # switch_voice -> repair
        _seg("drop", ["dropout"]),                   # resynthesize -> repair
        _seg("trans", ["bad_translation"]),          # retranslate -> not repair
    ]
    plan = build_remediation_plan(_report(segments))
    ids = set(plan["repair_directive"]["segment_ids"])
    assert ids == {"timbre", "drop"}
    assert "moss-tts-nano-onnx" in plan["repair_directive"]["tts_backends"]
    assert plan["summary"]["auto_fixable_count"] == 2
    assert plan["summary"]["manual_count"] == 2


def test_next_best_actions_prioritizes_auto_and_impact():
    segments = [
        _seg("t1", ["timbre_mismatch"]),
        _seg("t2", ["timbre_mismatch"]),
        _seg("u1", ["undubbed"], severity="P0"),
    ]
    plan = build_remediation_plan(_report(segments))
    # switch_voice covers 2 auto-fixable P1s (gain 4) and should rank first over
    # the single non-auto undubbed P0.
    assert plan["next_best_actions"][0]["action"] == ACTION_SWITCH_VOICE
    assert plan["actions"][0]["count"] == 2


def test_delivery_blockers_link_gates_to_segments():
    segments = [
        _seg("u1", ["undubbed"], severity="P0"),
        _seg("u2", ["undubbed"], severity="P0"),
        _seg("sp", ["timbre_mismatch"]),
    ]
    gates = [
        {"id": "undubbed_coverage", "status": "failed"},
        {"id": "speaker_consistency", "status": "review"},
        {"id": "coverage", "status": "passed"},  # passed -> excluded
    ]
    plan = build_remediation_plan(_report(segments, gates))
    blockers = {b["gate"]: b for b in plan["delivery_blockers"]}
    assert "coverage" not in blockers
    assert set(blockers["undubbed_coverage"]["segment_ids"]) == {"u1", "u2"}
    assert blockers["speaker_consistency"]["segment_ids"] == ["sp"]
