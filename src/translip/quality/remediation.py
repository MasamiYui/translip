"""Turn dub-QA defects into a structured remediation / optimization plan.

The dub-QA report tells you *what* is wrong per segment (issue tags + metrics).
This module turns that into *what to do about it*: for every problem segment it
picks the single highest-leverage next action, maps it onto a remediation
**executor** that genuinely exists in the pipeline, and aggregates everything
into a prioritized plan.

The plan is dual-purpose:

* **Human** — the UI renders prioritized "next best actions" and a per-segment
  recommendation (the prose is localized on the frontend from the codes + numbers
  emitted here, so this module stays i18n-neutral).
* **AI / automation** — the plan is a stable, machine-readable artifact. Its
  action vocabulary is aligned with ``repair/planner.py`` suggested actions and
  the real tunable knobs, and ``repair_directive`` is a ready-to-run handoff for
  ``run-dub-repair`` (segment ids + backends). An optimization loop reads this to
  decide the next iteration.

Pure functions only — ``build_remediation_plan(report)`` takes the QA report dict
and returns the plan dict. No I/O, no model calls.
"""

from __future__ import annotations

from typing import Any

REMEDIATION_VERSION = "remediation-v0"

# --- Issue tags (mirror dub_qa.ALL_ISSUES) --------------------------------- #
ISSUE_UNDUBBED = "undubbed"
ISSUE_TIMBRE = "timbre_mismatch"
ISSUE_DROPOUT = "dropout"
ISSUE_PACING = "pacing"
ISSUE_INTELLIGIBILITY = "low_intelligibility"
ISSUE_INAUDIBLE = "inaudible"
ISSUE_TRANSLATION = "bad_translation"

# --- Remediation actions --------------------------------------------------- #
ACTION_REWRITE = "rewrite_translation"      # shorten/simplify the target text
ACTION_RESYNTH = "resynthesize"             # regenerate TTS candidates (tournament)
ACTION_SWITCH_VOICE = "switch_voice"        # switch the speaker's reference audio
ACTION_SWITCH_BACKEND = "switch_tts_backend"
ACTION_REFIT = "refit_timeline"             # rendering knob (compression / rubberband)
ACTION_RETRANSLATE = "retranslate"          # re-run translation for the segment
ACTION_FILL = "fill_undubbed"               # force-synthesize a skipped segment
ACTION_MANUAL = "manual_review"

# --- Executors: who/what can actually perform the action ------------------- #
EX_REPAIR = "repair"    # run-dub-repair tournament (automated)
EX_EDITOR = "editor"    # dubbing-editor per-segment op (human-in-the-loop)
EX_RENDER = "render"    # render knob change + re-render (automated)
EX_RERUN = "rerun"      # re-run an upstream stage (translation / synthesis)
EX_MANUAL = "manual"    # needs a human decision

_SEVERITY_WEIGHT = {"P0": 3, "P1": 2, "P2": 1, "ok": 0}

# Map each action to the repair planner's suggested_action vocabulary, so the
# export can drive run-dub-repair directly. None == not a repair-driven action.
_REPAIR_ACTION = {
    ACTION_REWRITE: "rewrite_for_dubbing",
    ACTION_RESYNTH: "regenerate_candidates",
    ACTION_SWITCH_VOICE: "switch_reference_audio",
    ACTION_SWITCH_BACKEND: "switch_tts_backend",
}

# Actions an automated loop can attempt without human input.
_AUTO_ACTIONS = {
    ACTION_REWRITE,
    ACTION_RESYNTH,
    ACTION_SWITCH_VOICE,
    ACTION_SWITCH_BACKEND,
    ACTION_REFIT,
}

# Actions the run-dub-repair engine itself can carry out (subset of auto).
_REPAIR_DRIVEN = set(_REPAIR_ACTION)

_ACTION_EXECUTOR = {
    ACTION_REWRITE: EX_REPAIR,
    ACTION_RESYNTH: EX_REPAIR,
    ACTION_SWITCH_VOICE: EX_REPAIR,
    ACTION_SWITCH_BACKEND: EX_REPAIR,
    ACTION_REFIT: EX_RENDER,
    ACTION_RETRANSLATE: EX_RERUN,
    ACTION_FILL: EX_RERUN,
    ACTION_MANUAL: EX_MANUAL,
}

# Which segment issue tags each failed delivery gate is caused by. Lets the UI
# jump from "why is delivery blocked" straight to the offending segments.
_GATE_ISSUES = {
    "coverage": (ISSUE_INAUDIBLE, ISSUE_UNDUBBED),
    "undubbed_coverage": (ISSUE_UNDUBBED,),
    "speaker_consistency": (ISSUE_TIMBRE,),
    "character_voice": (ISSUE_TIMBRE,),
}

# Advisory knob hints for the render-refit action (the optimization signal).
_REFIT_KNOB = {
    "stage": "render",
    "params": {"fit_backend": "rubberband", "max_compress_ratio": "+0.15"},
}


def _num(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _primary_action(defects: set[str], seg: dict[str, Any]) -> str:
    """Pick the single highest-leverage next action for a segment.

    Ordered by what unblocks delivery and what the pipeline can most reliably
    fix; the full ``defects`` list is preserved separately so nothing is hidden.
    """
    if ISSUE_UNDUBBED in defects:
        return ACTION_FILL
    if ISSUE_INAUDIBLE in defects:
        return ACTION_REFIT
    if ISSUE_TIMBRE in defects:
        return ACTION_SWITCH_VOICE
    if ISSUE_DROPOUT in defects or ISSUE_INTELLIGIBILITY in defects:
        return ACTION_RESYNTH
    if ISSUE_PACING in defects:
        ratio = _num(seg.get("duration_ratio"))
        unfitted = seg.get("fit_strategy") == "overflow_unfitted"
        # The dub overruns its window and tempo-fitting could not absorb it →
        # shortening the text is the real fix; otherwise just re-fit harder.
        if unfitted or (ratio is not None and ratio > 1.3):
            return ACTION_REWRITE
        return ACTION_REFIT
    if ISSUE_TRANSLATION in defects:
        return ACTION_RETRANSLATE
    return ACTION_MANUAL


def _evidence(seg: dict[str, Any]) -> dict[str, Any]:
    """The numeric signals behind the verdict (used by UI prose + AI loop)."""
    return {
        "duration_ratio": _num(seg.get("duration_ratio")),
        "fit_strategy": seg.get("fit_strategy"),
        "speaker_similarity": _num(seg.get("speaker_similarity")),
        "text_similarity": _num(seg.get("text_similarity")),
        "dropout_ratio": _num(seg.get("dropout_ratio")),
        "subtitle_coverage_ratio": _num(seg.get("subtitle_coverage_ratio")),
        "judge_score": _num(seg.get("judge_score")),
    }


def _segment_directive(seg: dict[str, Any]) -> dict[str, Any] | None:
    defects = [tag for tag in seg.get("issue_tags") or [] if tag]
    if not defects:
        return None
    defect_set = set(defects)
    action = _primary_action(defect_set, seg)
    severity = seg.get("severity") if seg.get("severity") in _SEVERITY_WEIGHT else "P1"
    return {
        "segment_id": seg.get("segment_id"),
        "start": _num(seg.get("start")),
        "speaker_id": seg.get("speaker_id"),
        "severity": severity,
        "defects": defects,
        "primary_action": action,
        "executor": _ACTION_EXECUTOR[action],
        "repair_action": _REPAIR_ACTION.get(action),
        "auto_fixable": action in _AUTO_ACTIONS,
        "gain": _SEVERITY_WEIGHT.get(severity, 2),
        "knob": _REFIT_KNOB if action == ACTION_REFIT else None,
        "evidence": _evidence(seg),
    }


def _delivery_blockers(report: dict[str, Any], directives: list[dict[str, Any]]) -> list[dict[str, Any]]:
    scorecard = report.get("scorecard") or {}
    gates = scorecard.get("gates") if isinstance(scorecard.get("gates"), list) else []
    blockers: list[dict[str, Any]] = []
    for gate in gates:
        if not isinstance(gate, dict):
            continue
        if gate.get("status") not in ("failed", "review"):
            continue
        issues = _GATE_ISSUES.get(str(gate.get("id")))
        seg_ids: list[str] = []
        if issues:
            issue_set = set(issues)
            seg_ids = [
                str(d["segment_id"])
                for d in directives
                if d.get("segment_id") and issue_set.intersection(d.get("defects") or [])
            ]
        blockers.append(
            {
                "gate": gate.get("id"),
                "status": gate.get("status"),
                "segment_ids": seg_ids,
                "count": len(seg_ids),
            }
        )
    return blockers


def build_remediation_plan(report: dict[str, Any]) -> dict[str, Any]:
    """Derive the prioritized remediation/optimization plan from a dub-QA report."""
    segments = report.get("segments") if isinstance(report.get("segments"), list) else []
    directives = [d for d in (_segment_directive(s) for s in segments if isinstance(s, dict)) if d]

    # Aggregate by action, sorted so the highest-impact (and automatable) work
    # floats to the top.
    by_action: dict[str, dict[str, Any]] = {}
    for d in directives:
        action = d["primary_action"]
        group = by_action.setdefault(
            action,
            {
                "action": action,
                "executor": d["executor"],
                "repair_action": d["repair_action"],
                "auto_fixable": d["auto_fixable"],
                "knob": d["knob"],
                "segment_ids": [],
                "count": 0,
                "total_gain": 0,
            },
        )
        if d.get("segment_id"):
            group["segment_ids"].append(str(d["segment_id"]))
        group["count"] += 1
        group["total_gain"] += d["gain"]

    actions = sorted(
        by_action.values(),
        key=lambda g: (g["auto_fixable"], g["total_gain"], g["count"]),
        reverse=True,
    )
    next_best = [
        {
            "action": g["action"],
            "executor": g["executor"],
            "count": g["count"],
            "total_gain": g["total_gain"],
            "auto_fixable": g["auto_fixable"],
        }
        for g in actions[:3]
    ]

    # Concrete handoff for run-dub-repair: every auto-fixable segment the repair
    # engine can attempt, plus the recommended escalation backends.
    repair_segment_ids = [
        str(d["segment_id"])
        for d in directives
        if d.get("segment_id") and d["primary_action"] in _REPAIR_DRIVEN
    ]
    auto_fixable_count = sum(1 for d in directives if d["auto_fixable"])

    return {
        "version": REMEDIATION_VERSION,
        "summary": {
            "problem_count": len(directives),
            "auto_fixable_count": auto_fixable_count,
            "manual_count": len(directives) - auto_fixable_count,
            "recoverable_gain": sum(d["gain"] for d in directives if d["auto_fixable"]),
            "total_gain": sum(d["gain"] for d in directives),
        },
        "actions": actions,
        "next_best_actions": next_best,
        "delivery_blockers": _delivery_blockers(report, directives),
        "repair_directive": {
            "segment_ids": repair_segment_ids,
            "tts_backends": ["moss-tts-nano-onnx", "qwen3tts"],
            "include_risk": True,
            "attempts_per_item": 3,
        }
        if repair_segment_ids
        else None,
        "segment_directives": {
            str(d["segment_id"]): d for d in directives if d.get("segment_id")
        },
    }
