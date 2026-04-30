from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..pipeline.manifest import now_iso
from ..utils.files import ensure_directory


@dataclass(slots=True)
class DubBenchmarkRequest:
    pipeline_root: Path | str
    output_dir: Path | str
    target_lang: str = "en"

    def normalized(self) -> "DubBenchmarkRequest":
        return DubBenchmarkRequest(
            pipeline_root=Path(self.pipeline_root).expanduser().resolve(),
            output_dir=Path(self.output_dir).expanduser().resolve(),
            target_lang=self.target_lang,
        )


@dataclass(slots=True)
class DubBenchmarkArtifacts:
    benchmark_path: Path
    report_path: Path
    manifest_path: Path


@dataclass(slots=True)
class DubBenchmarkResult:
    request: DubBenchmarkRequest
    artifacts: DubBenchmarkArtifacts
    benchmark: dict[str, Any]
    manifest: dict[str, Any]


def build_dub_benchmark(request: DubBenchmarkRequest) -> DubBenchmarkResult:
    normalized = request.normalized()
    started_at = now_iso()
    started_monotonic = time.monotonic()
    output_dir = ensure_directory(Path(normalized.output_dir))
    benchmark_path = output_dir / f"dub_benchmark.{normalized.target_lang}.json"
    report_path = output_dir / f"dub_benchmark_report.{normalized.target_lang}.md"
    manifest_path = output_dir / "dub-benchmark-manifest.json"

    paths = _input_paths(normalized.pipeline_root, normalized.target_lang)
    mix_report = _read_json(paths["mix_report"])
    character_ledger = _read_json(paths["character_ledger"])
    repair_manifest = _read_json(paths["repair_manifest"])
    repair_attempts = _read_json(paths["repair_attempts"])
    manual_review = _read_json(paths["manual_review"])
    metrics = _metrics(
        mix_report=mix_report,
        character_ledger=character_ledger,
        repair_manifest=repair_manifest,
        repair_attempts=repair_attempts,
        manual_review=manual_review,
    )
    status, reasons = _status_and_reasons(metrics)
    benchmark = {
        "version": "dub-benchmark-v0",
        "created_at": now_iso(),
        "target_lang": normalized.target_lang,
        "status": status,
        "score": _score(metrics),
        "reasons": reasons,
        "metrics": metrics,
        "gates": _gates(metrics),
        "input": {
            key: str(path) if path is not None else None
            for key, path in paths.items()
        },
    }
    _write_json(benchmark_path, benchmark)
    report_path.write_text(_markdown_report(benchmark), encoding="utf-8")
    manifest = {
        "status": "succeeded",
        "target_lang": normalized.target_lang,
        "artifacts": {
            "benchmark": str(benchmark_path),
            "report": str(report_path),
        },
        "summary": {
            "status": status,
            "score": benchmark["score"],
            "reasons": reasons,
        },
        "timing": {
            "started_at": started_at,
            "finished_at": now_iso(),
            "elapsed_sec": round(time.monotonic() - started_monotonic, 3),
        },
        "error": None,
    }
    _write_json(manifest_path, manifest)
    return DubBenchmarkResult(
        request=normalized,
        artifacts=DubBenchmarkArtifacts(
            benchmark_path=benchmark_path,
            report_path=report_path,
            manifest_path=manifest_path,
        ),
        benchmark=benchmark,
        manifest=manifest,
    )


def _input_paths(root: Path, target_lang: str) -> dict[str, Path]:
    return {
        "mix_report": root / "task-e" / "voice" / f"mix_report.{target_lang}.json",
        "character_ledger": root / "task-d" / "voice" / "character-ledger" / f"character_ledger.{target_lang}.json",
        "repair_manifest": root / "task-d" / "voice" / "repair-run" / "repair-run-manifest.json",
        "repair_attempts": root / "task-d" / "voice" / "repair-run" / f"repair_attempts.{target_lang}.json",
        "manual_review": root / "task-d" / "voice" / "repair-run" / f"manual_review.{target_lang}.json",
    }


def _metrics(
    *,
    mix_report: dict[str, Any],
    character_ledger: dict[str, Any],
    repair_manifest: dict[str, Any],
    repair_attempts: dict[str, Any],
    manual_review: dict[str, Any],
) -> dict[str, Any]:
    stats = mix_report.get("stats", {}) if isinstance(mix_report.get("stats"), dict) else {}
    quality = stats.get("quality_summary", {}) if isinstance(stats.get("quality_summary"), dict) else {}
    audible = stats.get("audible_coverage", {}) if isinstance(stats.get("audible_coverage"), dict) else {}
    ledger_stats = character_ledger.get("stats", {}) if isinstance(character_ledger.get("stats"), dict) else {}
    repair_stats = repair_manifest.get("stats", {}) if isinstance(repair_manifest.get("stats"), dict) else {}
    if not repair_stats:
        repair_stats = repair_attempts.get("stats", {}) if isinstance(repair_attempts.get("stats"), dict) else {}
    if manual_review.get("stats"):
        manual_stats = manual_review.get("stats", {})
        repair_stats = {
            **repair_stats,
            "manual_required_count": manual_stats.get("manual_required_count", repair_stats.get("manual_required_count")),
        }

    total_count = _int(quality.get("total_count"))
    placed_count = _int(stats.get("placed_count"))
    skipped_count = _int(stats.get("skipped_count"))
    coverage_ratio = placed_count / max(total_count, 1)
    speaker_failed_count = _status_count(quality, "speaker_status_counts", "failed")
    intelligibility_failed_count = _status_count(quality, "intelligibility_status_counts", "failed")
    overall_failed_count = _status_count(quality, "overall_status_counts", "failed")
    return {
        "total_segment_count": total_count,
        "placed_count": placed_count,
        "skipped_count": skipped_count,
        "coverage_ratio": round(coverage_ratio, 4),
        "audible_failed_count": _int(audible.get("failed_count")),
        "audible_failed_segment_ids": audible.get("failed_segment_ids") if isinstance(audible.get("failed_segment_ids"), list) else [],
        "audible_min_coverage_ratio": _number(audible.get("min_coverage_ratio")),
        "audible_average_coverage_ratio": _number(audible.get("average_coverage_ratio")),
        "overall_failed_count": overall_failed_count,
        "overall_failed_ratio": round(overall_failed_count / max(total_count, 1), 4),
        "speaker_failed_count": speaker_failed_count,
        "speaker_failed_ratio": round(speaker_failed_count / max(total_count, 1), 4),
        "intelligibility_failed_count": intelligibility_failed_count,
        "intelligibility_failed_ratio": round(intelligibility_failed_count / max(total_count, 1), 4),
        "character_count": _int(ledger_stats.get("character_count")),
        "character_review_count": _int(ledger_stats.get("review_count")),
        "character_blocked_count": _int(ledger_stats.get("blocked_count")),
        "voice_mismatch_count": _int(ledger_stats.get("voice_mismatch_count")),
        "repair_attempt_count": _int(repair_stats.get("attempt_count")),
        "repair_selected_count": _int(repair_stats.get("selected_count")),
        "repair_manual_required_count": _int(repair_stats.get("manual_required_count")),
    }


def _status_and_reasons(metrics: dict[str, Any]) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if metrics["total_segment_count"] <= 0:
        reasons.append("no_rendered_segments")
    if metrics["coverage_ratio"] < 0.98:
        reasons.append("coverage_below_deliverable_threshold")
    if metrics["audible_failed_count"] > 0:
        reasons.append("audible_coverage_failed")
    if metrics["overall_failed_ratio"] > 0.05:
        reasons.append("upstream_failed_segments")
    if metrics["speaker_failed_ratio"] > 0.15:
        reasons.append("speaker_similarity_failed")
    if metrics["intelligibility_failed_ratio"] > 0.10:
        reasons.append("intelligibility_failed")
    if metrics["character_blocked_count"] > 0:
        reasons.append("character_voice_blocked")
    if metrics["character_review_count"] > 0 or metrics["voice_mismatch_count"] > 0:
        reasons.append("character_voice_review_required")
    if metrics["repair_manual_required_count"] > 0:
        reasons.append("repair_manual_required")

    if (
        metrics["total_segment_count"] <= 0
        or metrics["coverage_ratio"] < 0.98
        or metrics["audible_failed_count"] > 0
        or metrics["character_blocked_count"] > 0
    ):
        return "blocked", reasons
    if reasons:
        return "review_required", reasons
    return "deliverable_candidate", []


def _score(metrics: dict[str, Any]) -> float:
    penalty = 0.0
    penalty += max(0.0, 1.0 - float(metrics["coverage_ratio"])) * 60.0
    penalty += min(30.0, float(metrics["audible_failed_count"]) * 10.0)
    penalty += float(metrics["overall_failed_ratio"]) * 20.0
    penalty += float(metrics["speaker_failed_ratio"]) * 25.0
    penalty += float(metrics["intelligibility_failed_ratio"]) * 25.0
    penalty += min(20.0, float(metrics["character_review_count"]) * 4.0)
    penalty += min(25.0, float(metrics["character_blocked_count"]) * 10.0)
    penalty += min(20.0, float(metrics["voice_mismatch_count"]) * 5.0)
    penalty += min(15.0, float(metrics["repair_manual_required_count"]) * 3.0)
    return round(max(0.0, min(100.0, 100.0 - penalty)), 2)


def _gates(metrics: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "id": "coverage",
            "label": "Subtitle window audible coverage",
            "status": "passed" if metrics["coverage_ratio"] >= 0.98 and metrics["audible_failed_count"] == 0 else "failed",
            "value": metrics["coverage_ratio"],
            "threshold": ">=0.98 and audible_failed_count == 0",
        },
        {
            "id": "speaker_consistency",
            "label": "Speaker consistency failure ratio",
            "status": "passed" if metrics["speaker_failed_ratio"] <= 0.15 else "review",
            "value": metrics["speaker_failed_ratio"],
            "threshold": "<=0.15",
        },
        {
            "id": "character_voice",
            "label": "Character ledger voice risk",
            "status": "failed" if metrics["character_blocked_count"] > 0 else ("review" if metrics["character_review_count"] > 0 else "passed"),
            "value": {
                "review_count": metrics["character_review_count"],
                "blocked_count": metrics["character_blocked_count"],
                "voice_mismatch_count": metrics["voice_mismatch_count"],
            },
            "threshold": "blocked_count == 0 and review_count == 0",
        },
        {
            "id": "repair_tournament",
            "label": "Repair tournament unresolved items",
            "status": "review" if metrics["repair_manual_required_count"] > 0 else "passed",
            "value": metrics["repair_manual_required_count"],
            "threshold": "manual_required_count == 0",
        },
    ]


def _markdown_report(benchmark: dict[str, Any]) -> str:
    metrics = benchmark.get("metrics", {})
    lines = [
        "# Dub Benchmark Report",
        "",
        f"- status: `{benchmark.get('status')}`",
        f"- score: `{benchmark.get('score')}`",
        f"- reasons: `{', '.join(benchmark.get('reasons', [])) or '-'}`",
        "",
        "## Core Metrics",
        "",
        "| metric | value |",
        "| --- | --- |",
    ]
    for key in [
        "total_segment_count",
        "coverage_ratio",
        "audible_failed_count",
        "speaker_failed_ratio",
        "intelligibility_failed_ratio",
        "character_review_count",
        "character_blocked_count",
        "voice_mismatch_count",
        "repair_manual_required_count",
    ]:
        lines.append(f"| {key} | {metrics.get(key)} |")
    return "\n".join(lines) + "\n"


def _status_count(quality: dict[str, Any], key: str, status: str) -> int:
    counts = quality.get(key, {})
    if not isinstance(counts, dict):
        return 0
    return _int(counts.get(status))


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), 4)
    except (TypeError, ValueError):
        return None


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


__all__ = ["DubBenchmarkArtifacts", "DubBenchmarkRequest", "DubBenchmarkResult", "build_dub_benchmark"]
