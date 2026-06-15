"""Core engine: samples, media helpers, stage invocation, runner, run store."""
from __future__ import annotations

from .invoke import Invoker, StageResult, SubprocessInvoker, parse_kv
from .runner import run_suite
from .sample import GroundTruth, Sample, SampleManifest
from .scenario import (
    SCENARIO_REGISTRY,
    Scenario,
    ScenarioResult,
    available_scenarios,
    get_scenario,
    register_scenario,
)

__all__ = [
    "GroundTruth", "Sample", "SampleManifest",
    "Invoker", "StageResult", "SubprocessInvoker", "parse_kv",
    "Scenario", "ScenarioResult", "register_scenario", "get_scenario",
    "available_scenarios", "SCENARIO_REGISTRY",
    "run_suite",
]
