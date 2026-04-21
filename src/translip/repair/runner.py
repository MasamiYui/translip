from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..exceptions import TranslipError
from ..translation.glossary import load_glossary
from .export import now_iso, write_json
from .planner import build_repair_plan


@dataclass(slots=True)
class RepairPlanRequest:
    translation_path: Path | str
    profiles_path: Path | str
    task_d_report_paths: list[Path | str]
    output_dir: Path | str = Path("output-repair")
    target_lang: str = "en"
    glossary_path: Path | str | None = None
    max_items: int | None = None

    def normalized(self) -> "RepairPlanRequest":
        return RepairPlanRequest(
            translation_path=Path(self.translation_path).expanduser().resolve(),
            profiles_path=Path(self.profiles_path).expanduser().resolve(),
            task_d_report_paths=[
                Path(path).expanduser().resolve()
                for path in self.task_d_report_paths
            ],
            output_dir=Path(self.output_dir).expanduser().resolve(),
            target_lang=self.target_lang,
            glossary_path=(
                Path(self.glossary_path).expanduser().resolve()
                if self.glossary_path is not None
                else None
            ),
            max_items=self.max_items,
        )


@dataclass(slots=True)
class RepairPlanArtifacts:
    bundle_dir: Path
    repair_queue_path: Path
    rewrite_plan_path: Path
    reference_plan_path: Path
    manifest_path: Path


@dataclass(slots=True)
class RepairPlanResult:
    request: RepairPlanRequest
    artifacts: RepairPlanArtifacts
    manifest: dict[str, Any]


def plan_dub_repair(request: RepairPlanRequest) -> RepairPlanResult:
    normalized = _validate_request(request)
    bundle_dir = Path(normalized.output_dir)
    repair_queue_path = bundle_dir / f"repair_queue.{normalized.target_lang}.json"
    rewrite_plan_path = bundle_dir / f"rewrite_plan.{normalized.target_lang}.json"
    reference_plan_path = bundle_dir / f"reference_plan.{normalized.target_lang}.json"
    manifest_path = bundle_dir / "repair-plan-manifest.json"
    started_at = now_iso()
    started_monotonic = time.monotonic()

    translation_payload = _load_json(Path(normalized.translation_path))
    profiles_payload = _load_json(Path(normalized.profiles_path))
    task_d_reports = [_load_json(Path(path)) for path in normalized.task_d_report_paths]
    glossary = load_glossary(Path(normalized.glossary_path) if normalized.glossary_path else None)
    plan = build_repair_plan(
        translation_payload=translation_payload,
        profiles_payload=profiles_payload,
        task_d_reports=task_d_reports,
        target_lang=normalized.target_lang,
        glossary=glossary,
        max_items=normalized.max_items,
    )

    repair_queue = {
        "target_lang": normalized.target_lang,
        "source": {
            "translation_path": str(normalized.translation_path),
            "profiles_path": str(normalized.profiles_path),
            "task_d_reports": [str(path) for path in normalized.task_d_report_paths],
        },
        "stats": plan["stats"],
        "items": plan["items"],
    }
    rewrite_plan = {
        "target_lang": normalized.target_lang,
        "source_repair_queue": str(repair_queue_path),
        **plan["rewrite_plan"],
    }
    reference_plan = {
        "target_lang": normalized.target_lang,
        "source_repair_queue": str(repair_queue_path),
        **plan["reference_plan"],
    }
    write_json(repair_queue, repair_queue_path)
    write_json(rewrite_plan, rewrite_plan_path)
    write_json(reference_plan, reference_plan_path)

    manifest = {
        "status": "succeeded",
        "target_lang": normalized.target_lang,
        "artifacts": {
            "repair_queue": str(repair_queue_path),
            "rewrite_plan": str(rewrite_plan_path),
            "reference_plan": str(reference_plan_path),
        },
        "stats": plan["stats"],
        "timing": {
            "started_at": started_at,
            "finished_at": now_iso(),
            "elapsed_sec": round(time.monotonic() - started_monotonic, 3),
        },
    }
    write_json(manifest, manifest_path)
    return RepairPlanResult(
        request=normalized,
        artifacts=RepairPlanArtifacts(
            bundle_dir=bundle_dir,
            repair_queue_path=repair_queue_path,
            rewrite_plan_path=rewrite_plan_path,
            reference_plan_path=reference_plan_path,
            manifest_path=manifest_path,
        ),
        manifest=manifest,
    )


def _validate_request(request: RepairPlanRequest) -> RepairPlanRequest:
    normalized = request.normalized()
    if not Path(normalized.translation_path).exists():
        raise TranslipError(f"Translation file does not exist: {normalized.translation_path}")
    if not Path(normalized.profiles_path).exists():
        raise TranslipError(f"Profiles file does not exist: {normalized.profiles_path}")
    if not normalized.task_d_report_paths:
        raise TranslipError("task_d_report_paths must contain at least one Task D report")
    for path in normalized.task_d_report_paths:
        if not Path(path).exists():
            raise TranslipError(f"Task D report does not exist: {path}")
    if normalized.glossary_path is not None and not Path(normalized.glossary_path).exists():
        raise TranslipError(f"Glossary file does not exist: {normalized.glossary_path}")
    if normalized.max_items is not None and normalized.max_items <= 0:
        raise TranslipError("max_items must be greater than 0 when provided")
    return normalized


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


__all__ = [
    "RepairPlanArtifacts",
    "RepairPlanRequest",
    "RepairPlanResult",
    "plan_dub_repair",
]
