"""Scenario abstraction — "which translip capability, how to invoke, how to score".

A scenario is the glue between a stage and a metric. Subclasses implement
``invoke`` (run translip via the injected ``Invoker``) and ``score`` (compare the
stage outputs against the sample's ground truth → a metrics dict). The ``run``
template handles GT validation, timing, and error capture so subclasses stay
small. Scenarios self-register in ``SCENARIO_REGISTRY`` (add a capability = add a
file, mirroring translip's backend-registry philosophy).
"""
from __future__ import annotations

import time
import traceback
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .invoke import Invoker, StageResult
from .sample import Sample


@dataclass(slots=True)
class ScenarioResult:
    sample_id: str
    scenario: str
    status: str  # "succeeded" | "failed" | "skipped"
    metrics: dict[str, Any] = field(default_factory=dict)
    primary_metric: float | None = None
    duration_sec: float = 0.0
    output_dir: str | None = None
    error: str | None = None
    cached: bool = False
    stage_outputs: dict[str, str] = field(default_factory=dict)
    arm: str = "default"  # config-sweep variant label

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_id": self.sample_id,
            "scenario": self.scenario,
            "arm": self.arm,
            "status": self.status,
            "metrics": self.metrics,
            "primary_metric": self.primary_metric,
            "duration_sec": round(self.duration_sec, 3),
            "output_dir": self.output_dir,
            "error": self.error,
            "cached": self.cached,
            "stage_outputs": self.stage_outputs,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ScenarioResult":
        return cls(
            sample_id=data["sample_id"],
            scenario=data["scenario"],
            status=data["status"],
            metrics=data.get("metrics", {}),
            primary_metric=data.get("primary_metric"),
            duration_sec=data.get("duration_sec", 0.0),
            output_dir=data.get("output_dir"),
            error=data.get("error"),
            cached=data.get("cached", False),
            stage_outputs=data.get("stage_outputs", {}),
            arm=data.get("arm", "default"),
        )


class Scenario(ABC):
    name: str = "scenario"
    primary_metric_key: str = "score"
    higher_is_better: bool = True

    def required_gt(self) -> list[str]:
        """GroundTruth attribute names that must be present for this scenario."""
        return []

    def corpus_metrics(self, metrics_list: list[dict[str, Any]]) -> dict[str, Any]:
        """Corpus-level (micro) aggregates from succeeded per-sample metrics.

        Default: none. ASR/diarization/OCR override this to report the standard
        corpus-level CER/DER/F1 (pooled errors ÷ pooled denominator), which is the
        correct way to summarize these over a set — not a mean of per-sample rates.
        """
        return {}

    def input_paths(self, sample: Sample) -> list[str | Path]:
        """Files whose fingerprints feed the cache key (media + relevant GT)."""
        return [sample.media_path]

    @abstractmethod
    def invoke(self, sample: Sample, work_dir: Path, invoker: Invoker, *,
               config: dict[str, Any], timeout: float | None, log_path: Path | None) -> StageResult | None:
        ...

    @abstractmethod
    def score(self, sample: Sample, work_dir: Path, stage: StageResult | None,
              config: dict[str, Any]) -> dict[str, Any]:
        ...

    def _missing_gt(self, sample: Sample) -> list[str]:
        missing = []
        for attr in self.required_gt():
            value = getattr(sample.ground_truth, attr, None)
            if value is None or (isinstance(value, dict) and not value):
                missing.append(attr)
        return missing

    def run(self, sample: Sample, work_dir: Path, invoker: Invoker, *,
            config: dict[str, Any] | None = None, timeout: float | None = None) -> ScenarioResult:
        config = config or {}
        start = time.time()
        missing = self._missing_gt(sample)
        if missing:
            return ScenarioResult(
                sample_id=sample.sample_id, scenario=self.name, status="skipped",
                error=f"missing ground truth: {', '.join(missing)}",
                duration_sec=time.time() - start,
            )
        work_dir.mkdir(parents=True, exist_ok=True)
        log_path = work_dir / f"{self.name}.log"
        try:
            stage = self.invoke(sample, work_dir, invoker, config=config, timeout=timeout, log_path=log_path)
            if stage is not None and not stage.ok:
                return ScenarioResult(
                    sample_id=sample.sample_id, scenario=self.name, status="failed",
                    error=f"stage exit {stage.returncode}: {stage.stderr_tail()}",
                    duration_sec=time.time() - start, output_dir=str(work_dir),
                    stage_outputs=stage.outputs if stage else {},
                )
            metrics = self.score(sample, work_dir, stage, config)
            primary = metrics.get(self.primary_metric_key)
            primary = float(primary) if isinstance(primary, (int, float)) else None
            return ScenarioResult(
                sample_id=sample.sample_id, scenario=self.name, status="succeeded",
                metrics=metrics, primary_metric=primary,
                duration_sec=time.time() - start, output_dir=str(work_dir),
                stage_outputs=stage.outputs if stage else {},
            )
        except Exception as exc:  # noqa: BLE001 — surface any failure as a failed result, never crash the run
            return ScenarioResult(
                sample_id=sample.sample_id, scenario=self.name, status="failed",
                error=f"{type(exc).__name__}: {exc}\n{traceback.format_exc()[-800:]}",
                duration_sec=time.time() - start, output_dir=str(work_dir),
            )


SCENARIO_REGISTRY: dict[str, Scenario] = {}


def register_scenario(scenario: Scenario) -> Scenario:
    SCENARIO_REGISTRY[scenario.name] = scenario
    return scenario


def get_scenario(name: str) -> Scenario:
    if name not in SCENARIO_REGISTRY:
        raise KeyError(f"unknown scenario '{name}'. Available: {sorted(SCENARIO_REGISTRY)}")
    return SCENARIO_REGISTRY[name]


def available_scenarios() -> list[str]:
    return sorted(SCENARIO_REGISTRY)
