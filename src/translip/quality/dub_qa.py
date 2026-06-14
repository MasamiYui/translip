"""Per-segment dub quality analysis (the "evaluation / 实验分析" feature).

Unlike :mod:`translip.quality.dub_benchmark`, which produces an *aggregate*
scorecard consumed by the pipeline, this module joins the per-stage artifacts
back together by ``segment_id`` to answer the operator's concrete questions:

* which segments were never dubbed (left out of the final mix)?
* which have a timbre / speaker mismatch?
* which dropped words (the synthesized audio doesn't read back the translation)?
* which are paced badly (over/under stretched)?
* which are inaudible inside their subtitle window?
* which have a poor translation (optional LLM judge)?

It reuses the aggregate :func:`build_dub_benchmark` for the headline score and
adds these per-segment dimensions on top, writing ``dub_qa_report.{lang}.json``
plus a short markdown summary. Nothing here runs ML models except the optional
translation judge; everything else is a cheap on-disk join.
"""

from __future__ import annotations

import difflib
import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Reports the active evaluation phase: (step, total, phase_key). Steps are
# 1-based; `total` reflects only the phases actually planned for this run.
PhaseCallback = Callable[[int, int, str], None]

from ..exceptions import BackendUnavailableError
from ..pipeline.manifest import now_iso
from ..translation.backend import output_tag_for_language
from ..utils.files import ensure_directory
from .dub_benchmark import DubBenchmarkRequest, build_dub_benchmark
from .remediation import build_remediation_plan
from .translation_judge import JUDGE_FAIL_THRESHOLD, build_translation_judge

QA_VERSION = "dub-qa-v0"

# Issue tags surfaced per segment.
ISSUE_UNDUBBED = "undubbed"
ISSUE_TIMBRE = "timbre_mismatch"
ISSUE_DROPOUT = "dropout"
ISSUE_PACING = "pacing"
ISSUE_INTELLIGIBILITY = "low_intelligibility"
ISSUE_INAUDIBLE = "inaudible"
ISSUE_TRANSLATION = "bad_translation"
ALL_ISSUES = (
    ISSUE_UNDUBBED,
    ISSUE_TIMBRE,
    ISSUE_DROPOUT,
    ISSUE_PACING,
    ISSUE_INTELLIGIBILITY,
    ISSUE_INAUDIBLE,
    ISSUE_TRANSLATION,
)

# Heuristic thresholds.
DROPOUT_RATIO_THRESHOLD = 0.34  # >~1/3 of target tokens missing in the read-back
DROPOUT_MIN_TOKENS = 4  # ignore very short segments (ASR noise dominates)
INAUDIBLE_COVERAGE_THRESHOLD = 0.50
# A placed dub this much longer than its window is overflowing hard: tempo-fitting
# either over-accelerates the speech or the tail gets cut. ``duration_status``
# only *fails* outside [0.55, 1.65], so segments in the 1.45–1.65 band slip
# through as "review" — yet that band is where most perceived tail-trim damage
# lives. Flagging it here routes those segments to the rewrite/repair loop.
SEVERE_OVERFLOW_RATIO = 1.45

# Severity of each issue (highest wins for a segment's overall severity).
_ISSUE_SEVERITY = {
    ISSUE_UNDUBBED: "P0",
    ISSUE_TIMBRE: "P1",
    ISSUE_INTELLIGIBILITY: "P1",
    ISSUE_DROPOUT: "P1",
    ISSUE_INAUDIBLE: "P1",
    ISSUE_TRANSLATION: "P1",
    ISSUE_PACING: "P2",
}
_SEVERITY_ORDER = {"P0": 3, "P1": 2, "P2": 1, "ok": 0}

_TOKEN_RE = re.compile(r"[a-z0-9]+|[\u4e00-\u9fff]|[\u3040-\u30ff]+")


@dataclass(slots=True)
class DubQaRequest:
    pipeline_root: Path | str
    output_dir: Path | str
    target_lang: str = "en"
    source_lang: str = "zh"
    run_translation_judge: bool = False
    judge_path: Path | str | None = None

    def normalized(self) -> "DubQaRequest":
        return DubQaRequest(
            pipeline_root=Path(self.pipeline_root).expanduser().resolve(),
            output_dir=Path(self.output_dir).expanduser().resolve(),
            target_lang=self.target_lang,
            source_lang=self.source_lang,
            run_translation_judge=self.run_translation_judge,
            judge_path=Path(self.judge_path).expanduser().resolve() if self.judge_path else None,
        )


@dataclass(slots=True)
class DubQaArtifacts:
    report_path: Path
    manifest_path: Path
    markdown_path: Path
    benchmark_path: Path
    judge_path: Path | None = None
    remediation_path: Path | None = None


@dataclass(slots=True)
class DubQaResult:
    request: DubQaRequest
    artifacts: DubQaArtifacts
    report: dict[str, Any]
    manifest: dict[str, Any]


def build_dub_qa(request: DubQaRequest, *, on_phase: PhaseCallback | None = None) -> DubQaResult:
    normalized = request.normalized()
    started_at = now_iso()
    started_monotonic = time.monotonic()
    root = Path(normalized.pipeline_root)
    target_lang = normalized.target_lang
    output_dir = ensure_directory(Path(normalized.output_dir))

    report_path = output_dir / f"dub_qa_report.{target_lang}.json"
    markdown_path = output_dir / f"dub_qa_report.{target_lang}.md"
    manifest_path = output_dir / "dub-qa-manifest.json"

    # Sequential phases for honest step-based progress. The translation judge
    # is only planned (and counted) when explicitly requested; the rest always
    # run (the three enrichments are best-effort but still occupy a step).
    phases: list[str] = []
    if normalized.run_translation_judge:
        phases.append("judge")
    phases.extend(["scorecard", "segments", "remediation", "embeddings", "pitch", "mel"])

    def _phase(name: str) -> None:
        if on_phase is None or name not in phases:
            return
        try:
            on_phase(phases.index(name) + 1, len(phases), name)
        except Exception:  # pragma: no cover - progress is best-effort
            pass

    mix_report_path = root / "render" / "voice" / f"mix_report.{target_lang}.json"
    mix_report = _read_json(mix_report_path)
    translation_path = _resolve_translation_path(root, mix_report, target_lang)

    # 1) Optional (paid) translation judge.
    _phase("judge")
    judge_path, judge_status = _maybe_judge(
        normalized=normalized,
        translation_path=translation_path,
        output_dir=output_dir,
    )

    # 2) Aggregate scorecard (reuses the pipeline benchmark, fresh copy in our dir).
    _phase("scorecard")
    benchmark_dir = ensure_directory(output_dir / "benchmark")
    benchmark_result = build_dub_benchmark(
        DubBenchmarkRequest(
            pipeline_root=root,
            output_dir=benchmark_dir,
            target_lang=target_lang,
        )
    )

    # 3) Per-segment join.
    _phase("segments")
    placed = _as_list(mix_report.get("placed_segments"))
    skipped = _as_list(mix_report.get("skipped_segments"))
    translation_index = _index_segments(_read_json(translation_path) if translation_path else {})
    backread_index = _build_backread_index(root, mix_report, placed, skipped)
    judge_index = _build_judge_index(judge_path)

    rows = _build_rows(
        placed=placed,
        skipped=skipped,
        translation_index=translation_index,
        backread_index=backread_index,
        judge_index=judge_index,
        pipeline_root=root,
    )
    qa_summary = _summarize(rows, mix_report=mix_report, judge_status=judge_status)

    # Full-track audio paths for the original-vs-dub waveform compare. The
    # isolated original vocal sits next to separation's background output
    # (background.<fmt> -> voice.<fmt>); the dub full track is render's output.
    original_voice_rel = _original_voice_rel(mix_report, root)
    background_rel = _background_rel(mix_report, root)
    dub_voice_path = root / "render" / "voice" / f"dub_voice.{target_lang}.wav"
    dub_voice_rel = _rel_to_root(dub_voice_path, root) if dub_voice_path.exists() else None

    report = {
        "version": QA_VERSION,
        "created_at": now_iso(),
        "target_lang": target_lang,
        "source_lang": normalized.source_lang,
        "scorecard": benchmark_result.benchmark,
        "qa_summary": qa_summary,
        "segments": rows,
        "input": {
            "mix_report": str(mix_report_path) if mix_report_path.exists() else None,
            "translation": str(translation_path) if translation_path else None,
            "judge_scores": str(judge_path) if judge_path else None,
            "benchmark": str(benchmark_result.artifacts.benchmark_path),
            # Full-track audio for the original-vs-dub waveform comparison
            # (paths relative to the task output root, streamable as artifacts).
            "original_voice": original_voice_rel,
            "dub_voice": dub_voice_rel,
            # Pure background bed (separation accompaniment, no dialogue) so the UI
            # can A/B the instrumental track against original/dub.
            "background": background_rel,
        },
    }
    # Turn the per-segment defects into a prioritized remediation/optimization
    # plan — embedded in the report for the UI and written as a standalone,
    # machine-readable artifact an optimization loop / run-dub-repair can consume.
    _phase("remediation")
    remediation = build_remediation_plan(report)
    report["remediation"] = remediation
    remediation_path = output_dir / f"remediation_plan.{target_lang}.json"
    _write_json(remediation_path, remediation)
    # Best-effort: enrich the report with raw ECAPA speaker embeddings so the
    # UI can render an embedding scatter (PCA projection). Failures are
    # silently noted via report["embedding_meta"] without breaking dub-qa.
    _phase("embeddings")
    try:
        from .dub_embeddings import enrich_report_with_embeddings

        enrich_report_with_embeddings(report, pipeline_root=root)
    except Exception as exc:  # pragma: no cover - never fail the report write
        report["embedding_meta"] = {"status": "error", "reason": str(exc)}
    # Best-effort: extract per-segment F0 (pitch) contours via librosa.pyin so
    # the UI can render an original-vs-dub melody comparison. Same defensive
    # handling as the embedding enrichment above.
    _phase("pitch")
    try:
        from .dub_pitch import enrich_report_with_pitch

        enrich_report_with_pitch(report, pipeline_root=root)
    except Exception as exc:  # pragma: no cover - never fail the report write
        report["pitch_meta"] = {"status": "error", "reason": str(exc)}
    # Best-effort: extract per-segment mel spectrograms (uint8 quantized) so the UI
    # can render side-by-side spectrogram heatmaps for an acoustic texture sanity
    # check. Same defensive handling as the pitch enrichment above.
    _phase("mel")
    try:
        from .dub_mel import enrich_report_with_mel

        enrich_report_with_mel(report, pipeline_root=root)
    except Exception as exc:  # pragma: no cover - never fail the report write
        report["mel_meta"] = {"status": "error", "reason": str(exc)}
    _write_json(report_path, report)
    markdown_path.write_text(_markdown_report(report), encoding="utf-8")

    manifest = {
        "status": "succeeded",
        "target_lang": target_lang,
        "artifacts": {
            "report": str(report_path),
            "markdown": str(markdown_path),
            "benchmark": str(benchmark_result.artifacts.benchmark_path),
            "remediation": str(remediation_path),
            "judge_scores": str(judge_path) if judge_path else None,
        },
        "summary": {
            "score": benchmark_result.benchmark.get("score"),
            "status": benchmark_result.benchmark.get("status"),
            "problem_segment_count": qa_summary["problem_segment_count"],
            "issue_counts": qa_summary["issue_counts"],
            "judge_status": judge_status,
        },
        "timing": {
            "started_at": started_at,
            "finished_at": now_iso(),
            "elapsed_sec": round(time.monotonic() - started_monotonic, 3),
        },
        "error": None,
    }
    _write_json(manifest_path, manifest)

    return DubQaResult(
        request=normalized,
        artifacts=DubQaArtifacts(
            report_path=report_path,
            manifest_path=manifest_path,
            markdown_path=markdown_path,
            benchmark_path=benchmark_result.artifacts.benchmark_path,
            judge_path=judge_path,
            remediation_path=remediation_path,
        ),
        report=report,
        manifest=manifest,
    )


# --------------------------------------------------------------------------- #
# Translation judge orchestration
# --------------------------------------------------------------------------- #


def _maybe_judge(
    *,
    normalized: DubQaRequest,
    translation_path: Path | None,
    output_dir: Path,
) -> tuple[Path | None, str]:
    """Return ``(judge_scores_path, status)``.

    Status is one of: ``provided``, ``generated``, ``skipped``,
    ``unavailable`` (missing API key / call failed), ``no_translation``.
    """
    if normalized.judge_path is not None:
        path = Path(normalized.judge_path)
        return (path if path.exists() else None, "provided" if path.exists() else "skipped")
    if not normalized.run_translation_judge:
        return None, "skipped"
    if translation_path is None or not Path(translation_path).exists():
        return None, "no_translation"
    try:
        path = build_translation_judge(
            translation_path=translation_path,
            output_dir=output_dir,
            target_lang=normalized.target_lang,
            source_lang=normalized.source_lang,
        )
    except BackendUnavailableError:
        return None, "unavailable"
    if path is None:
        return None, "no_translation"
    return path, "generated"


# --------------------------------------------------------------------------- #
# Per-segment join
# --------------------------------------------------------------------------- #


def _build_rows(
    *,
    placed: list[dict[str, Any]],
    skipped: list[dict[str, Any]],
    translation_index: dict[str, dict[str, Any]],
    backread_index: dict[str, str],
    judge_index: dict[str, dict[str, Any]],
    pipeline_root: Path,
) -> list[dict[str, Any]]:
    placed_by_id = {str(it.get("segment_id") or ""): it for it in placed if it.get("segment_id")}
    skipped_by_id = {str(it.get("segment_id") or ""): it for it in skipped if it.get("segment_id")}

    # The universe is everything that *should* be dubbed: every translated segment,
    # plus anything the renderer reported. A translated segment that never reached
    # the mix (e.g. its speaker was dropped before synthesis) is an undubbed line —
    # the exact "有些地方没配" failure operators want to find.
    universe: list[str] = list(translation_index.keys())
    for sid in [*placed_by_id, *skipped_by_id]:
        if sid and sid not in translation_index:
            universe.append(sid)

    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for sid in universe:
        if not sid or sid in seen:
            continue
        seen.add(sid)
        if sid in placed_by_id:
            item, placed_flag = placed_by_id[sid], True
        elif sid in skipped_by_id:
            item, placed_flag = skipped_by_id[sid], False
        else:
            item, placed_flag = _synthetic_undubbed_item(sid, translation_index.get(sid, {})), False
        rows.append(
            _build_row(
                item,
                placed=placed_flag,
                translation_index=translation_index,
                backread_index=backread_index,
                judge_index=judge_index,
                pipeline_root=pipeline_root,
            )
        )
    rows.sort(key=lambda r: (r.get("start") if isinstance(r.get("start"), (int, float)) else 1e12))
    return rows


def _synthetic_undubbed_item(segment_id: str, translation: dict[str, Any]) -> dict[str, Any]:
    """A mix-item-shaped stub for a translated segment that never reached the mix."""
    return {
        "segment_id": segment_id,
        "anchor_start": translation.get("start"),
        "anchor_end": translation.get("end"),
        "target_text": translation.get("target_text"),
        "speaker_id": translation.get("speaker_label"),
        "mix_status": "not_synthesized",
        "audio_path": None,
    }


def _build_row(
    item: dict[str, Any],
    *,
    placed: bool,
    translation_index: dict[str, dict[str, Any]],
    backread_index: dict[str, str],
    judge_index: dict[str, dict[str, Any]],
    pipeline_root: Path,
) -> dict[str, Any]:
    segment_id = str(item.get("segment_id") or "")
    translation = translation_index.get(segment_id, {})
    source_text = str(translation.get("source_text") or "")
    target_text = str(item.get("target_text") or translation.get("target_text") or "")
    backread_text = backread_index.get(segment_id, "")
    judge = judge_index.get(segment_id, {})

    start = _coalesce_number(item.get("anchor_start"), translation.get("start"))
    end = _coalesce_number(item.get("anchor_end"), translation.get("end"))
    duration = round(end - start, 3) if isinstance(start, (int, float)) and isinstance(end, (int, float)) else None

    subtitle_coverage = _number(item.get("subtitle_coverage_ratio"))
    duration_ratio = _segment_duration_ratio(item)

    dropout_count, dropout_total, dropout_ratio = _dropout(target_text, backread_text)

    row: dict[str, Any] = {
        "segment_id": segment_id,
        "speaker_id": item.get("speaker_id") or translation.get("speaker_label"),
        "start": start,
        "end": end,
        "duration": duration,
        "source_text": source_text,
        "target_text": target_text,
        "backread_text": backread_text,
        "dub_audio_path": _rel_to_root(item.get("audio_path"), pipeline_root),
        "reference_audio_path": _rel_to_root(item.get("reference_path"), pipeline_root),
        "placed": placed,
        "mix_status": item.get("mix_status"),
        "fit_strategy": item.get("fit_strategy"),
        "overall_status": item.get("overall_status"),
        "speaker_status": item.get("speaker_status"),
        "intelligibility_status": item.get("intelligibility_status"),
        "duration_status": item.get("duration_status"),
        "speaker_similarity": _number(item.get("speaker_similarity")),
        "text_similarity": _number(item.get("text_similarity")),
        "duration_ratio": duration_ratio,
        # Timeline-fit detail for the per-segment duration bar: original window
        # vs the dub's actual placed footprint (post atempo/stretch).
        "source_duration_sec": _number(item.get("source_duration_sec")),
        "generated_duration_sec": _number(item.get("generated_duration_sec")),
        "fitted_duration_sec": _number(item.get("fitted_duration_sec")),
        "trimmed_tail_sec": _number(item.get("trimmed_tail_sec")),
        "trimmed_speech_sec": _number(item.get("trimmed_speech_sec")),
        "placement_start": _coalesce_number(item.get("placement_start")),
        "placement_end": _coalesce_number(item.get("placement_end")),
        "subtitle_coverage_ratio": subtitle_coverage,
        "qa_flags": item.get("qa_flags") if isinstance(item.get("qa_flags"), list) else [],
        "dropout_token_count": dropout_count,
        "dropout_total_tokens": dropout_total,
        "dropout_ratio": dropout_ratio,
        "judge_score": _number(judge.get("score")),
        "judge_adequacy": _number(judge.get("adequacy")),
        "judge_fluency": _number(judge.get("fluency")),
        "judge_reason": judge.get("reason"),
    }
    issue_tags = _issue_tags(row)
    row["issue_tags"] = issue_tags
    row["severity"] = _row_severity(issue_tags)
    return row


def _issue_tags(row: dict[str, Any]) -> list[str]:
    tags: list[str] = []
    if not row["placed"]:
        # A line that never made it into the final mix, but only counts as a
        # problem when there was actually something to say.
        if row.get("source_text") or row.get("target_text"):
            tags.append(ISSUE_UNDUBBED)
    else:
        if row.get("speaker_status") == "failed":
            tags.append(ISSUE_TIMBRE)
        if row.get("intelligibility_status") == "failed":
            tags.append(ISSUE_INTELLIGIBILITY)
        if (
            row.get("backread_text")
            and row["dropout_total_tokens"] >= DROPOUT_MIN_TOKENS
            and row["dropout_ratio"] >= DROPOUT_RATIO_THRESHOLD
        ):
            tags.append(ISSUE_DROPOUT)
        ratio = row.get("duration_ratio")
        severe_overflow = (
            isinstance(ratio, (int, float)) and ratio >= SEVERE_OVERFLOW_RATIO
        ) or row.get("fit_strategy") == "overflow_unfitted"
        if row.get("duration_status") == "failed" or severe_overflow:
            tags.append(ISSUE_PACING)
        coverage = row.get("subtitle_coverage_ratio")
        if isinstance(coverage, (int, float)) and coverage < INAUDIBLE_COVERAGE_THRESHOLD:
            tags.append(ISSUE_INAUDIBLE)
    judge_score = row.get("judge_score")
    if isinstance(judge_score, (int, float)) and judge_score < JUDGE_FAIL_THRESHOLD:
        tags.append(ISSUE_TRANSLATION)
    return tags


def _row_severity(issue_tags: list[str]) -> str:
    severity = "ok"
    for tag in issue_tags:
        candidate = _ISSUE_SEVERITY.get(tag, "P2")
        if _SEVERITY_ORDER[candidate] > _SEVERITY_ORDER[severity]:
            severity = candidate
    return severity


# --------------------------------------------------------------------------- #
# Summary
# --------------------------------------------------------------------------- #


def _summarize(
    rows: list[dict[str, Any]],
    *,
    mix_report: dict[str, Any],
    judge_status: str,
) -> dict[str, Any]:
    issue_counts = {issue: 0 for issue in ALL_ISSUES}
    severity_counts = {"P0": 0, "P1": 0, "P2": 0, "ok": 0}
    dropout_ratios: list[float] = []
    judge_scores: list[float] = []
    problem_segment_count = 0
    dubbed_count = 0
    for row in rows:
        for tag in row["issue_tags"]:
            if tag in issue_counts:
                issue_counts[tag] += 1
        severity_counts[row["severity"]] = severity_counts.get(row["severity"], 0) + 1
        if row["issue_tags"]:
            problem_segment_count += 1
        if row.get("placed"):
            dubbed_count += 1
        if row.get("dropout_total_tokens", 0) >= DROPOUT_MIN_TOKENS:
            dropout_ratios.append(float(row["dropout_ratio"]))
        if isinstance(row.get("judge_score"), (int, float)):
            judge_scores.append(float(row["judge_score"]))

    # Timeline pressure: how much the dub overruns its windows and how much
    # audio is actually lost to tail-trimming. This is the perceived-quality
    # dimension the headline score under-weights, so surface it explicitly.
    overflow_ratios: list[float] = []
    severe_overflow_count = 0
    unfitted_count = 0
    cut_audio_sec = 0.0
    lost_speech_sec = 0.0
    silence_only_trim_count = 0
    for row in rows:
        if not row.get("placed"):
            continue
        ratio = row.get("duration_ratio")
        if isinstance(ratio, (int, float)) and ratio > 1.0:
            overflow_ratios.append(float(ratio))
        if isinstance(ratio, (int, float)) and ratio >= SEVERE_OVERFLOW_RATIO:
            severe_overflow_count += 1
        if row.get("fit_strategy") == "overflow_unfitted":
            unfitted_count += 1
            generated = row.get("generated_duration_sec")
            fitted = row.get("fitted_duration_sec")
            if isinstance(generated, (int, float)) and isinstance(fitted, (int, float)):
                cut_audio_sec += max(0.0, float(generated) - float(fitted))
            # ``cut_audio_sec`` conflates time-stretch shrink with real
            # truncation, so it over-reports loss. ``lost_speech_sec`` is the
            # honest signal: of the tail actually cut, how much was speech (vs
            # trailing silence). This is the number that should trend to zero.
            trimmed_tail = row.get("trimmed_tail_sec")
            if isinstance(trimmed_tail, (int, float)) and trimmed_tail > 0.0:
                trimmed_speech = row.get("trimmed_speech_sec")
                if isinstance(trimmed_speech, (int, float)) and trimmed_speech > 0.0:
                    lost_speech_sec += float(trimmed_speech)
                else:
                    silence_only_trim_count += 1
    timeline = {
        "overflow_segment_count": len(overflow_ratios),
        "severe_overflow_count": severe_overflow_count,
        "unfitted_count": unfitted_count,
        "max_duration_ratio": round(max(overflow_ratios), 4) if overflow_ratios else None,
        "avg_overflow_ratio": round(sum(overflow_ratios) / len(overflow_ratios), 4) if overflow_ratios else None,
        "cut_audio_sec": round(cut_audio_sec, 3),
        # Speech actually dropped to tail-trim (silence trims excluded) — the
        # perceived-loss metric the overhaul targets at zero.
        "lost_speech_sec": round(lost_speech_sec, 3),
        "silence_only_trim_count": silence_only_trim_count,
    }

    stats = mix_report.get("stats", {}) if isinstance(mix_report.get("stats"), dict) else {}
    skip_reason_counts = stats.get("skip_reason_counts", {}) if isinstance(stats.get("skip_reason_counts"), dict) else {}
    total = len(rows)

    translation_judge = None
    if judge_scores or judge_status in {"generated", "provided"}:
        translation_judge = {
            "status": judge_status,
            "scored_count": len(judge_scores),
            "failed_count": issue_counts[ISSUE_TRANSLATION],
            "average_score": round(sum(judge_scores) / len(judge_scores), 3) if judge_scores else None,
            "min_score": min(judge_scores) if judge_scores else None,
        }

    return {
        "segment_count": total,
        "problem_segment_count": problem_segment_count,
        "issue_counts": issue_counts,
        "severity_counts": severity_counts,
        "skip_reason_counts": skip_reason_counts,
        # End-to-end coverage anchored on the translation universe, which is more
        # honest than the renderer's own denominator: a line that was translated
        # but never synthesized still counts as not-dubbed here.
        "coverage": {
            "translated_count": total,
            "dubbed_count": dubbed_count,
            "undubbed_count": total - dubbed_count,
            "coverage_ratio": round(dubbed_count / total, 4) if total else None,
        },
        "dropout": {
            "affected_count": issue_counts[ISSUE_DROPOUT],
            "average_ratio": round(sum(dropout_ratios) / len(dropout_ratios), 4) if dropout_ratios else None,
        },
        "timeline": timeline,
        # Perceptual companion to dub_benchmark._score (which is pipeline hygiene):
        # this one is driven by what a viewer actually hears — tail-trim loss and
        # severe overflow — so a clean-but-cut run no longer looks deliverable.
        "perceptual_score": _perceptual_score(
            timeline=timeline,
            undubbed_count=max(0, total - dubbed_count),
            segment_count=total,
        ),
        "translation_judge": translation_judge,
        "judge_status": judge_status,
    }


def _perceptual_score(*, timeline: dict[str, Any], undubbed_count: int, segment_count: int) -> float:
    """A 0–100 perceptual score that, unlike the hygiene score, penalizes the
    audible defects: dub audio lost to tail-trimming, severe overflow (sped-up or
    unfitted lines), and lines that were translated but never dubbed. Deliberately
    separate from ``dub_benchmark._score`` so historical scores stay comparable;
    each term is capped so one dimension can't single-handedly zero the score.
    """
    if segment_count <= 0:
        return 100.0
    cut_sec = float(timeline.get("cut_audio_sec") or 0.0)
    severe = int(timeline.get("severe_overflow_count") or 0)
    cut_penalty = min(40.0, cut_sec)  # ~1 pt per second of dub audio thrown away
    severe_penalty = min(35.0, (severe / segment_count) * 60.0)
    undubbed_penalty = min(25.0, (undubbed_count / segment_count) * 60.0)
    return round(max(0.0, 100.0 - cut_penalty - severe_penalty - undubbed_penalty), 1)


# --------------------------------------------------------------------------- #
# Resolution / indexing helpers
# --------------------------------------------------------------------------- #


def _resolve_translation_path(root: Path, mix_report: dict[str, Any], target_lang: str) -> Path | None:
    recorded = mix_report.get("input", {}).get("translation_path") if isinstance(mix_report.get("input"), dict) else None
    if recorded:
        candidate = Path(recorded)
        if candidate.exists():
            return candidate
    tag = output_tag_for_language(target_lang)
    task_c = root / "translation"
    if task_c.exists():
        for candidate in sorted(task_c.rglob(f"translation.{tag}.json")):
            if candidate.is_file():
                return candidate
    return None


def _build_backread_index(
    root: Path,
    mix_report: dict[str, Any],
    placed: list[dict[str, Any]],
    skipped: list[dict[str, Any]],
) -> dict[str, str]:
    report_paths: list[Path] = []

    def _add(path_str: Any) -> None:
        if not path_str:
            return
        path = Path(str(path_str))
        if path.exists() and path.is_file() and path not in report_paths:
            report_paths.append(path)

    input_block = mix_report.get("input", {}) if isinstance(mix_report.get("input"), dict) else {}
    for path_str in input_block.get("task_d_report_paths", []) or []:
        _add(path_str)
    for item in [*placed, *skipped]:
        _add(item.get("task_d_report_path"))
    if not report_paths:
        task_d = root / "synthesis"
        if task_d.exists():
            for candidate in sorted(task_d.rglob("*.json")):
                payload = _read_json(candidate)
                if isinstance(payload.get("segments"), list) and any(
                    "backread_text" in seg for seg in payload["segments"] if isinstance(seg, dict)
                ):
                    report_paths.append(candidate)

    index: dict[str, str] = {}
    for path in report_paths:
        payload = _read_json(path)
        for seg in _as_list(payload.get("segments")):
            seg_id = str(seg.get("segment_id") or "")
            backread = str(seg.get("backread_text") or "").strip()
            if seg_id and backread and not index.get(seg_id):
                index[seg_id] = backread
    return index


def _build_judge_index(judge_path: Path | None) -> dict[str, dict[str, Any]]:
    if judge_path is None:
        return {}
    payload = _read_json(judge_path)
    index: dict[str, dict[str, Any]] = {}
    for row in _as_list(payload.get("scores")):
        seg_id = str(row.get("segment_id") or "")
        if seg_id:
            index[seg_id] = row
    return index


def _index_segments(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for seg in _as_list(payload.get("segments")):
        seg_id = str(seg.get("segment_id") or "")
        if seg_id:
            index[seg_id] = seg
    return index


# --------------------------------------------------------------------------- #
# Dropout / numeric helpers
# --------------------------------------------------------------------------- #


def _dropout(target_text: str, backread_text: str) -> tuple[int, int, float]:
    target_tokens = _TOKEN_RE.findall(target_text.lower())
    if not target_tokens:
        return 0, 0, 0.0
    backread_tokens = _TOKEN_RE.findall(backread_text.lower())
    matcher = difflib.SequenceMatcher(a=target_tokens, b=backread_tokens, autojunk=False)
    missing = 0
    for tag, i1, i2, _j1, _j2 in matcher.get_opcodes():
        if tag in ("delete", "replace"):
            missing += i2 - i1
    return missing, len(target_tokens), round(missing / len(target_tokens), 4)


def _segment_duration_ratio(item: dict[str, Any]) -> float | None:
    generated = item.get("generated_duration_sec")
    source = item.get("source_duration_sec")
    if isinstance(generated, (int, float)) and isinstance(source, (int, float)) and source > 0:
        return round(float(generated) / float(source), 4)
    return None


def _original_voice_rel(mix_report: dict[str, Any], root: Path) -> str | None:
    """Resolve the separation isolated-vocal track from the mix report's background path.

    Stage1 writes ``voice.<fmt>`` and ``background.<fmt>`` side by side; the mix
    report records the background path, so the original vocal is its sibling.
    """
    background = ((mix_report.get("input") or {}).get("background_path"))
    if not background:
        return None
    background_path = Path(str(background))
    voice_path = background_path.with_name(f"voice{background_path.suffix}")
    if not voice_path.exists():
        return None
    return _rel_to_root(voice_path, root)


def _background_rel(mix_report: dict[str, Any], root: Path) -> str | None:
    """Resolve the separation pure-background (accompaniment, no dialogue) track.

    Stage1 writes ``background.<fmt>`` next to the isolated vocal; the mix report
    records that background path directly.
    """
    background = ((mix_report.get("input") or {}).get("background_path"))
    if not background:
        return None
    background_path = Path(str(background))
    if not background_path.exists():
        return None
    return _rel_to_root(background_path, root)


def _rel_to_root(path_str: Any, root: Path) -> str | None:
    if not path_str:
        return None
    path = Path(str(path_str))
    try:
        return str(path.resolve().relative_to(root))
    except (ValueError, OSError):
        return str(path)


def _coalesce_number(*values: Any) -> float | None:
    for value in values:
        if isinstance(value, (int, float)):
            return round(float(value), 3)
    return None


def _number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), 4)
    except (TypeError, ValueError):
        return None


def _as_list(value: Any) -> list[dict[str, Any]]:
    return value if isinstance(value, list) else []


def _read_json(path: Path | None) -> dict[str, Any]:
    if path is None or not Path(path).exists() or not Path(path).is_file():
        return {}
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _markdown_report(report: dict[str, Any]) -> str:
    summary = report.get("qa_summary", {})
    scorecard = report.get("scorecard", {})
    issue_counts = summary.get("issue_counts", {})
    lines = [
        "# Dub QA Report",
        "",
        f"- score: `{scorecard.get('score')}`  status: `{scorecard.get('status')}`",
        f"- segments: `{summary.get('segment_count')}`  with issues: `{summary.get('problem_segment_count')}`",
        f"- judge: `{summary.get('judge_status')}`",
        "",
        "## Issue breakdown",
        "",
        "| issue | count |",
        "| --- | --- |",
    ]
    for issue in ALL_ISSUES:
        lines.append(f"| {issue} | {issue_counts.get(issue, 0)} |")
    lines.extend(["", "## Worst segments", "", "| start | severity | issues | segment |", "| --- | --- | --- | --- |"])
    worst = sorted(
        (row for row in report.get("segments", []) if row.get("issue_tags")),
        key=lambda r: (-_SEVERITY_ORDER.get(r.get("severity", "ok"), 0), r.get("start") or 0),
    )[:20]
    for row in worst:
        start = row.get("start")
        start_str = f"{start:.1f}s" if isinstance(start, (int, float)) else "-"
        issues = ", ".join(row.get("issue_tags", []))
        lines.append(f"| {start_str} | {row.get('severity')} | {issues} | {row.get('segment_id')} |")
    return "\n".join(lines) + "\n"


__all__ = [
    "ALL_ISSUES",
    "DubQaArtifacts",
    "DubQaRequest",
    "DubQaResult",
    "QA_VERSION",
    "build_dub_qa",
]
