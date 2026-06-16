"""Config-sweep (arms): runner fans out over arms; sweep report marks the winner."""
from __future__ import annotations

from translip_lab.config import LabConfig
from translip_lab.core.invoke import StageResult
from translip_lab.core.runner import run_suite
from translip_lab.core.sample import Sample, SampleManifest
from translip_lab.core.scenario import Scenario
from translip_lab.report import sweep_to_markdown


class FakeInvoker:
    def translip(self, *a, **k):
        return StageResult([], 0, "", "", 0.0, {})

    def module(self, *a, **k):
        return StageResult([], 0, "", "", 0.0, {})


class ArmAwareScenario(Scenario):
    name = "fake"
    primary_metric_key = "cer"
    higher_is_better = False

    def invoke(self, sample, work_dir, invoker, *, config, timeout, log_path):
        return invoker.translip("run", [])

    def score(self, sample, work_dir, stage, config):
        return {"cer": 0.4 if config.get("model") == "tiny" else 0.2}


def _cfg(tmp_path):
    return LabConfig(home=tmp_path, datasets_dir=tmp_path / "d", runs_dir=tmp_path / "r",
                     cache_dir=tmp_path / "c", translip_cmd=("x",), python_cmd=("y",))


def test_sweep_fans_out_over_arms(tmp_path):
    media = tmp_path / "a.wav"
    media.write_bytes(b"x")
    manifest = SampleManifest("t", [Sample("s1", media)])
    arms = [
        {"label": "tiny", "scenario_config": {"fake": {"model": "tiny"}}},
        {"label": "small", "scenario_config": {"fake": {"model": "small"}}},
    ]
    man = run_suite(manifest=manifest, scenarios=[ArmAwareScenario()], suite="sw",
                    invoker=FakeInvoker(), lab_config=_cfg(tmp_path), arms=arms, use_cache=False)

    assert man["arms"] == ["tiny", "small"]
    assert man["aggregates"]["fake@tiny"]["mean"] == 0.4
    assert man["aggregates"]["fake@small"]["mean"] == 0.2
    assert {r["arm"] for r in man["results"]} == {"tiny", "small"}

    md = sweep_to_markdown(man)
    assert "Sweep" in md and "🏆" in md  # winner (small, lower CER) marked


def test_default_arm_keeps_bare_key(tmp_path):
    media = tmp_path / "a.wav"
    media.write_bytes(b"x")
    manifest = SampleManifest("t", [Sample("s1", media)])
    man = run_suite(manifest=manifest, scenarios=[ArmAwareScenario()], suite="sw",
                    invoker=FakeInvoker(), lab_config=_cfg(tmp_path), use_cache=False)
    assert man["arms"] == ["default"]
    assert "fake" in man["aggregates"]  # bare scenario key, not fake@default
    assert sweep_to_markdown(man) == ""  # single arm → no sweep section
