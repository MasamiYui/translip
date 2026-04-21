from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from ..dubbing.backend import ReferencePackage, SynthSegmentInput, TTSBackend
from ..dubbing.metrics import SegmentEvaluation, evaluate_segment
from ..dubbing.moss_tts_nano_backend import MossTtsNanoOnnxBackend
from ..dubbing.qwen_tts_backend import QwenTTSBackend
from ..dubbing.reference import ReferenceCandidate, prepare_reference_package
from ..exceptions import TranslipError
from .export import now_iso, write_json


Evaluator = Callable[..., SegmentEvaluation]


@dataclass(slots=True)
class RepairRunRequest:
    repair_queue_path: Path | str
    rewrite_plan_path: Path | str
    reference_plan_path: Path | str
    output_dir: Path | str = Path("output-repair-run")
    tts_backends: list[str] = field(default_factory=lambda: ["moss-tts-nano-onnx"])
    device: str = "auto"
    backread_model: str = "tiny"
    segment_ids: list[str] | None = None
    max_items: int | None = 10
    attempts_per_item: int = 3
    include_risk: bool = False
    keep_intermediate: bool = False

    def normalized(self) -> "RepairRunRequest":
        return RepairRunRequest(
            repair_queue_path=Path(self.repair_queue_path).expanduser().resolve(),
            rewrite_plan_path=Path(self.rewrite_plan_path).expanduser().resolve(),
            reference_plan_path=Path(self.reference_plan_path).expanduser().resolve(),
            output_dir=Path(self.output_dir).expanduser().resolve(),
            tts_backends=[str(backend) for backend in self.tts_backends],
            device=self.device,
            backread_model=self.backread_model,
            segment_ids=list(self.segment_ids) if self.segment_ids else None,
            max_items=self.max_items,
            attempts_per_item=self.attempts_per_item,
            include_risk=self.include_risk,
            keep_intermediate=self.keep_intermediate,
        )


@dataclass(slots=True)
class RepairRunArtifacts:
    bundle_dir: Path
    attempts_path: Path
    selected_segments_path: Path
    manual_review_path: Path
    manifest_path: Path


@dataclass(slots=True)
class RepairRunResult:
    request: RepairRunRequest
    artifacts: RepairRunArtifacts
    manifest: dict[str, Any]


def run_dub_repair(
    request: RepairRunRequest,
    *,
    backend_override: TTSBackend | None = None,
    evaluator: Evaluator = evaluate_segment,
) -> RepairRunResult:
    normalized = _validate_request(request)
    bundle_dir = Path(normalized.output_dir)
    target_lang = "en"
    attempts_path = bundle_dir / f"repair_attempts.{target_lang}.json"
    selected_segments_path = bundle_dir / f"selected_segments.{target_lang}.json"
    manual_review_path = bundle_dir / f"manual_review.{target_lang}.json"
    manifest_path = bundle_dir / "repair-run-manifest.json"
    started_at = now_iso()
    started_monotonic = time.monotonic()

    repair_queue = _load_json(Path(normalized.repair_queue_path))
    rewrite_plan = _load_json(Path(normalized.rewrite_plan_path))
    reference_plan = _load_json(Path(normalized.reference_plan_path))
    target_lang = str(repair_queue.get("target_lang") or target_lang)
    attempts_path = bundle_dir / f"repair_attempts.{target_lang}.json"
    selected_segments_path = bundle_dir / f"selected_segments.{target_lang}.json"
    manual_review_path = bundle_dir / f"manual_review.{target_lang}.json"

    rewrite_by_segment = _rewrite_by_segment(rewrite_plan)
    reference_by_speaker = _reference_by_speaker(reference_plan)
    items = _selected_repair_items(
        repair_queue,
        include_risk=normalized.include_risk,
        segment_ids=normalized.segment_ids,
        max_items=normalized.max_items,
    )
    backend_cache: dict[str, TTSBackend] = {}
    reference_cache: dict[str, ReferencePackage] = {}
    item_results: list[dict[str, Any]] = []
    selected_segments: list[dict[str, Any]] = []
    manual_items: list[dict[str, Any]] = []

    for item in items:
        item_result = _repair_item(
            item=item,
            rewrite_candidates=rewrite_by_segment.get(str(item.get("segment_id") or ""), []),
            speaker_reference_plan=reference_by_speaker.get(str(item.get("speaker_id") or ""), {}),
            target_lang=target_lang,
            request=normalized,
            bundle_dir=bundle_dir,
            backend_cache=backend_cache,
            reference_cache=reference_cache,
            backend_override=backend_override,
            evaluator=evaluator,
        )
        item_results.append(item_result)
        selected = item_result.get("selected_attempt")
        if isinstance(selected, dict):
            selected_segments.append(_selected_segment_payload(item=item, attempt=selected))
        else:
            manual_items.append(_manual_review_payload(item=item, item_result=item_result))

    attempts_payload = {
        "target_lang": target_lang,
        "source": {
            "repair_queue": str(normalized.repair_queue_path),
            "rewrite_plan": str(normalized.rewrite_plan_path),
            "reference_plan": str(normalized.reference_plan_path),
        },
        "stats": _attempt_stats(item_results=item_results, input_count=len(items), manual_count=len(manual_items)),
        "items": item_results,
    }
    selected_payload = {
        "target_lang": target_lang,
        "source_repair_attempts": str(attempts_path),
        "stats": {
            "selected_count": len(selected_segments),
            "input_count": len(items),
        },
        "segments": selected_segments,
    }
    manual_payload = {
        "target_lang": target_lang,
        "source_repair_attempts": str(attempts_path),
        "stats": {
            "manual_required_count": len(manual_items),
            "input_count": len(items),
        },
        "items": manual_items,
    }
    write_json(attempts_payload, attempts_path)
    write_json(selected_payload, selected_segments_path)
    write_json(manual_payload, manual_review_path)

    manifest = {
        "status": "succeeded",
        "target_lang": target_lang,
        "artifacts": {
            "repair_attempts": str(attempts_path),
            "selected_segments": str(selected_segments_path),
            "manual_review": str(manual_review_path),
        },
        "stats": attempts_payload["stats"],
        "timing": {
            "started_at": started_at,
            "finished_at": now_iso(),
            "elapsed_sec": round(time.monotonic() - started_monotonic, 3),
        },
    }
    write_json(manifest, manifest_path)
    return RepairRunResult(
        request=normalized,
        artifacts=RepairRunArtifacts(
            bundle_dir=bundle_dir,
            attempts_path=attempts_path,
            selected_segments_path=selected_segments_path,
            manual_review_path=manual_review_path,
            manifest_path=manifest_path,
        ),
        manifest=manifest,
    )


def _repair_item(
    *,
    item: dict[str, Any],
    rewrite_candidates: list[dict[str, Any]],
    speaker_reference_plan: dict[str, Any],
    target_lang: str,
    request: RepairRunRequest,
    bundle_dir: Path,
    backend_cache: dict[str, TTSBackend],
    reference_cache: dict[str, ReferencePackage],
    backend_override: TTSBackend | None,
    evaluator: Evaluator,
) -> dict[str, Any]:
    segment_id = str(item.get("segment_id") or "")
    attempt_specs = _attempt_specs(
        item=item,
        rewrite_candidates=rewrite_candidates,
        speaker_reference_plan=speaker_reference_plan,
        tts_backends=request.tts_backends,
        attempts_per_item=request.attempts_per_item,
    )
    attempts: list[dict[str, Any]] = []
    for index, spec in enumerate(attempt_specs, start=1):
        attempt_id = f"attempt-{index:04d}"
        output_path = bundle_dir / "repair_candidates" / str(item.get("speaker_id") or "unknown") / segment_id / f"{attempt_id}.wav"
        attempt = _run_attempt(
            item=item,
            spec=spec,
            attempt_id=attempt_id,
            output_path=output_path,
            target_lang=target_lang,
            request=request,
            bundle_dir=bundle_dir,
            backend_cache=backend_cache,
            reference_cache=reference_cache,
            backend_override=backend_override,
            evaluator=evaluator,
        )
        attempts.append(attempt)

    selected = _select_attempt(attempts)
    for attempt in attempts:
        if selected is not None and attempt.get("attempt_id") == selected.get("attempt_id"):
            attempt["status"] = "selected"
        elif attempt.get("status") == "candidate":
            attempt["status"] = "rejected"

    return {
        "segment_id": segment_id,
        "speaker_id": str(item.get("speaker_id") or ""),
        "queue_class": str(item.get("queue_class") or ""),
        "strict_blocker": bool(item.get("strict_blocker")),
        "failure_reasons": list(item.get("failure_reasons", [])),
        "suggested_actions": list(item.get("suggested_actions", [])),
        "attempt_count": len(attempts),
        "repair_status": "candidate_selected" if selected is not None else "manual_required",
        "selected_attempt_id": selected.get("attempt_id") if selected else None,
        "selected_attempt": selected,
        "attempts": attempts,
    }


def _run_attempt(
    *,
    item: dict[str, Any],
    spec: dict[str, Any],
    attempt_id: str,
    output_path: Path,
    target_lang: str,
    request: RepairRunRequest,
    bundle_dir: Path,
    backend_cache: dict[str, TTSBackend],
    reference_cache: dict[str, ReferencePackage],
    backend_override: TTSBackend | None,
    evaluator: Evaluator,
) -> dict[str, Any]:
    segment_id = str(item.get("segment_id") or "")
    target_text = str(spec["target_text"])
    backend_name = str(spec["backend"])
    reference_path = str(spec["reference_path"])
    try:
        backend = backend_override or _backend_for(backend_name, request=request, backend_cache=backend_cache)
        reference = _reference_for(
            reference_row=spec["reference"],
            request=request,
            reference_cache=reference_cache,
            bundle_dir=bundle_dir,
        )
        segment = SynthSegmentInput(
            segment_id=segment_id,
            speaker_id=str(item.get("speaker_id") or ""),
            target_lang=target_lang,
            target_text=target_text,
            source_duration_sec=float(item.get("source_duration_sec") or 0.0),
            duration_budget_sec=float(spec.get("estimated_tts_duration_sec") or item.get("source_duration_sec") or 0.0),
            qa_flags=[str(reason) for reason in item.get("failure_reasons", [])],
            metadata={
                "repair_attempt_id": attempt_id,
                "rewrite_id": spec.get("rewrite_id"),
                "text_variant": spec.get("text_variant"),
            },
        )
        synth_output = backend.synthesize(reference=reference, segment=segment, output_path=output_path)
        evaluation = evaluator(
            reference_audio_path=reference.original_audio_path,
            generated_audio_path=synth_output.audio_path,
            target_text=target_text,
            target_lang=target_lang,
            source_duration_sec=segment.source_duration_sec,
            requested_device=request.device,
            backread_model_name=request.backread_model,
        )
        payload = {
            "attempt_id": attempt_id,
            "segment_id": segment_id,
            "status": "candidate",
            "target_text": target_text,
            "text_variant": spec.get("text_variant"),
            "rewrite_id": spec.get("rewrite_id"),
            "backend": getattr(backend, "backend_name", backend_name),
            "resolved_model": getattr(backend, "resolved_model", ""),
            "resolved_device": getattr(backend, "resolved_device", request.device),
            "reference_path": reference_path,
            "audio_path": str(synth_output.audio_path),
            "generated_duration_sec": round(float(synth_output.generated_duration_sec), 3),
            "metrics": _evaluation_payload(evaluation),
            "score": _attempt_score(evaluation),
            "strict_accepted": evaluation.overall_status in {"passed", "review"},
            "error": None,
        }
        return payload
    except Exception as exc:  # pragma: no cover - exercised by real backend failures
        return {
            "attempt_id": attempt_id,
            "segment_id": segment_id,
            "status": "failed",
            "target_text": target_text,
            "text_variant": spec.get("text_variant"),
            "rewrite_id": spec.get("rewrite_id"),
            "backend": backend_name,
            "reference_path": reference_path,
            "audio_path": str(output_path),
            "generated_duration_sec": 0.0,
            "metrics": {},
            "score": 0.0,
            "strict_accepted": False,
            "error": str(exc),
        }


def _attempt_specs(
    *,
    item: dict[str, Any],
    rewrite_candidates: list[dict[str, Any]],
    speaker_reference_plan: dict[str, Any],
    tts_backends: list[str],
    attempts_per_item: int,
) -> list[dict[str, Any]]:
    text_rows = _text_rows(item=item, rewrite_candidates=rewrite_candidates)
    reference_rows = _reference_rows(item=item, speaker_reference_plan=speaker_reference_plan)
    specs: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for text_row in text_rows:
        for reference_row in reference_rows:
            for backend in tts_backends:
                key = (
                    str(text_row["target_text"]).casefold(),
                    str(reference_row["path"]),
                    str(backend),
                )
                if key in seen:
                    continue
                seen.add(key)
                specs.append(
                    {
                        **text_row,
                        "backend": backend,
                        "reference_path": str(reference_row["path"]),
                        "reference": reference_row,
                    }
                )
                if len(specs) >= attempts_per_item:
                    return specs
    return specs


def _text_rows(*, item: dict[str, Any], rewrite_candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    actions = {str(action) for action in item.get("suggested_actions", [])}
    if "rewrite_for_dubbing" in actions or "merge_short_segments" in actions:
        for candidate in rewrite_candidates:
            target_text = str(candidate.get("target_text") or "").strip()
            if target_text:
                rows.append(
                    {
                        "target_text": target_text,
                        "text_variant": str(candidate.get("variant") or "rewrite"),
                        "rewrite_id": candidate.get("rewrite_id"),
                        "estimated_tts_duration_sec": candidate.get("estimated_tts_duration_sec"),
                    }
                )
    current_text = str(item.get("target_text") or "").strip()
    if current_text:
        rows.append(
            {
                "target_text": current_text,
                "text_variant": "current",
                "rewrite_id": None,
                "estimated_tts_duration_sec": None,
            }
        )
    return _dedupe_text_rows(rows)


def _reference_rows(*, item: dict[str, Any], speaker_reference_plan: dict[str, Any]) -> list[dict[str, Any]]:
    speaker_id = str(item.get("speaker_id") or speaker_reference_plan.get("speaker_id") or "")
    candidates = [
        {**row, "speaker_id": speaker_id}
        for row in speaker_reference_plan.get("candidates", [])
        if isinstance(row, dict) and row.get("path")
    ]
    recommended = str(speaker_reference_plan.get("recommended_reference_path") or "")
    current = str(item.get("reference_path") or speaker_reference_plan.get("current_reference_path") or "")
    ordered: list[dict[str, Any]] = []
    for path in [recommended, current]:
        match = _find_reference_row(candidates, path)
        if match is not None:
            ordered.append(match)
    ordered.extend(candidates)
    if not ordered and current:
        ordered.append(
            {
                "path": current,
                "speaker_id": speaker_id,
                "profile_id": "",
                "duration_sec": 0.0,
                "text": "",
                "rms": 0.0,
                "quality_score": 0.0,
                "selection_reason": "fallback_current_reference",
            }
        )
    return _dedupe_reference_rows(ordered)


def _reference_for(
    *,
    reference_row: dict[str, Any],
    request: RepairRunRequest,
    reference_cache: dict[str, ReferencePackage],
    bundle_dir: Path,
) -> ReferencePackage:
    path = str(reference_row["path"])
    cached = reference_cache.get(path)
    if cached is not None:
        return cached
    candidate = ReferenceCandidate(
        profile_id=str(reference_row.get("profile_id") or ""),
        speaker_id=str(reference_row.get("speaker_id") or ""),
        path=Path(path).expanduser().resolve(),
        text=str(reference_row.get("text") or ""),
        duration_sec=float(reference_row.get("duration_sec") or 0.0),
        rms=float(reference_row.get("rms") or 0.0),
        score=float(reference_row.get("quality_score") or 0.0),
        selection_reason=str(reference_row.get("selection_reason") or "repair_reference"),
    )
    prepared = prepare_reference_package(
        candidate,
        output_path=(
            bundle_dir
            / "prepared_references"
            / f"{candidate.profile_id or candidate.speaker_id or 'reference'}_{candidate.path.stem}_prepared.wav"
        ),
    )
    reference_cache[path] = prepared
    return prepared


def _backend_for(
    backend_name: str,
    *,
    request: RepairRunRequest,
    backend_cache: dict[str, TTSBackend],
) -> TTSBackend:
    cached = backend_cache.get(backend_name)
    if cached is not None:
        return cached
    if backend_name == "moss-tts-nano-onnx":
        backend: TTSBackend = MossTtsNanoOnnxBackend(requested_device=request.device)
    elif backend_name == "qwen3tts":
        backend = QwenTTSBackend(requested_device=request.device)
    else:
        raise TranslipError(f"Unsupported repair TTS backend: {backend_name}")
    backend_cache[backend_name] = backend
    return backend


def _selected_repair_items(
    repair_queue: dict[str, Any],
    *,
    include_risk: bool,
    segment_ids: list[str] | None,
    max_items: int | None,
) -> list[dict[str, Any]]:
    allowed = set(segment_ids or [])
    items = [
        item
        for item in repair_queue.get("items", [])
        if (
            isinstance(item, dict)
            and (include_risk or bool(item.get("strict_blocker")))
            and (not allowed or str(item.get("segment_id") or "") in allowed)
        )
    ]
    if max_items is not None:
        items = items[:max(0, max_items)]
    return items


def _select_attempt(attempts: list[dict[str, Any]]) -> dict[str, Any] | None:
    accepted = [
        attempt
        for attempt in attempts
        if attempt.get("strict_accepted") and attempt.get("status") == "candidate"
    ]
    if not accepted:
        return None
    return max(accepted, key=lambda attempt: (float(attempt.get("score") or 0.0), -_status_rank(attempt)))


def _status_rank(attempt: dict[str, Any]) -> int:
    overall_status = str(attempt.get("metrics", {}).get("overall_status") or "")
    return {"passed": 0, "review": 1, "failed": 2}.get(overall_status, 3)


def _selected_segment_payload(*, item: dict[str, Any], attempt: dict[str, Any]) -> dict[str, Any]:
    metrics = attempt.get("metrics", {})
    return {
        "segment_id": item.get("segment_id"),
        "speaker_id": item.get("speaker_id"),
        "target_text": attempt.get("target_text"),
        "selected_audio_path": attempt.get("audio_path"),
        "selected_source": "repair_candidate",
        "selected_attempt_id": attempt.get("attempt_id"),
        "backend": attempt.get("backend"),
        "reference_path": attempt.get("reference_path"),
        "generated_duration_sec": attempt.get("generated_duration_sec"),
        "duration_ratio": metrics.get("duration_ratio"),
        "duration_status": metrics.get("duration_status"),
        "speaker_similarity": metrics.get("speaker_similarity"),
        "speaker_status": metrics.get("speaker_status"),
        "backread_text": metrics.get("backread_text"),
        "text_similarity": metrics.get("text_similarity"),
        "intelligibility_status": metrics.get("intelligibility_status"),
        "overall_status": metrics.get("overall_status"),
        "score": attempt.get("score"),
        "strict_accepted": True,
    }


def _manual_review_payload(*, item: dict[str, Any], item_result: dict[str, Any]) -> dict[str, Any]:
    return {
        "segment_id": item.get("segment_id"),
        "speaker_id": item.get("speaker_id"),
        "source_text": item.get("source_text"),
        "target_text": item.get("target_text"),
        "queue_class": item.get("queue_class"),
        "failure_reasons": item.get("failure_reasons", []),
        "suggested_actions": item.get("suggested_actions", []),
        "attempt_count": item_result.get("attempt_count", 0),
        "best_attempt": _best_attempt(item_result.get("attempts", [])),
        "decision": "manual_required",
    }


def _best_attempt(attempts: list[dict[str, Any]]) -> dict[str, Any] | None:
    candidates = [attempt for attempt in attempts if attempt.get("status") != "failed"]
    if not candidates:
        return None
    return max(candidates, key=lambda attempt: float(attempt.get("score") or 0.0))


def _evaluation_payload(evaluation: SegmentEvaluation) -> dict[str, Any]:
    return {
        "duration_ratio": round(float(evaluation.duration_ratio), 3),
        "duration_status": evaluation.duration_status,
        "speaker_similarity": (
            round(float(evaluation.speaker_similarity), 4)
            if evaluation.speaker_similarity is not None
            else None
        ),
        "speaker_status": evaluation.speaker_status,
        "backread_text": evaluation.backread_text,
        "text_similarity": round(float(evaluation.text_similarity), 4),
        "intelligibility_status": evaluation.intelligibility_status,
        "overall_status": evaluation.overall_status,
    }


def _attempt_score(evaluation: SegmentEvaluation) -> float:
    status_weight = {"passed": 2.5, "review": 1.2, "failed": 0.0}.get(evaluation.overall_status, 0.0)
    duration_score = max(0.0, 1.0 - abs(1.0 - float(evaluation.duration_ratio)))
    speaker_score = max(0.0, float(evaluation.speaker_similarity or 0.0))
    text_score = max(0.0, float(evaluation.text_similarity or 0.0))
    return round(status_weight + duration_score * 0.35 + speaker_score * 0.25 + text_score * 0.4, 4)


def _attempt_stats(*, item_results: list[dict[str, Any]], input_count: int, manual_count: int) -> dict[str, Any]:
    attempt_count = sum(int(item.get("attempt_count") or 0) for item in item_results)
    selected_count = sum(1 for item in item_results if item.get("selected_attempt_id"))
    status_counts: dict[str, int] = {}
    for item in item_results:
        status = str(item.get("repair_status") or "")
        status_counts[status] = status_counts.get(status, 0) + 1
    return {
        "input_count": input_count,
        "attempt_count": attempt_count,
        "selected_count": selected_count,
        "manual_required_count": manual_count,
        "repair_status_counts": dict(sorted(status_counts.items())),
    }


def _rewrite_by_segment(rewrite_plan: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    rows: dict[str, list[dict[str, Any]]] = {}
    for item in rewrite_plan.get("items", []):
        if not isinstance(item, dict):
            continue
        segment_id = str(item.get("segment_id") or "")
        rows[segment_id] = [
            candidate
            for candidate in item.get("rewrite_candidates", [])
            if isinstance(candidate, dict)
        ]
    return rows


def _reference_by_speaker(reference_plan: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("speaker_id") or ""): item
        for item in reference_plan.get("speakers", [])
        if isinstance(item, dict) and item.get("speaker_id")
    }


def _find_reference_row(candidates: list[dict[str, Any]], path: str) -> dict[str, Any] | None:
    if not path:
        return None
    normalized = Path(path).expanduser().resolve()
    for candidate in candidates:
        if Path(str(candidate.get("path"))).expanduser().resolve() == normalized:
            return candidate
    return None


def _dedupe_text_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        key = str(row.get("target_text") or "").casefold()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def _dedupe_reference_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[Path] = set()
    for row in rows:
        path = Path(str(row.get("path") or "")).expanduser().resolve()
        if not str(row.get("path") or "") or path in seen:
            continue
        seen.add(path)
        deduped.append(row)
    return deduped


def _validate_request(request: RepairRunRequest) -> RepairRunRequest:
    normalized = request.normalized()
    for path in [normalized.repair_queue_path, normalized.rewrite_plan_path, normalized.reference_plan_path]:
        if not Path(path).exists():
            raise TranslipError(f"Repair run input does not exist: {path}")
    if not normalized.tts_backends:
        raise TranslipError("At least one repair TTS backend is required")
    if normalized.max_items is not None and normalized.max_items <= 0:
        raise TranslipError("max_items must be greater than 0 when provided")
    if normalized.attempts_per_item <= 0:
        raise TranslipError("attempts_per_item must be greater than 0")
    return normalized


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


__all__ = [
    "RepairRunArtifacts",
    "RepairRunRequest",
    "RepairRunResult",
    "run_dub_repair",
]
