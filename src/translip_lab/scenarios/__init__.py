"""Capability scenarios — import side-effects populate SCENARIO_REGISTRY."""
from __future__ import annotations

from ..core.scenario import available_scenarios, get_scenario, register_scenario

# Importing each module registers its scenario.
from . import asr, diarization, e2e_dub, ocr_detect, separation, subtitle_erase  # noqa: E402,F401

__all__ = ["get_scenario", "register_scenario", "available_scenarios"]
