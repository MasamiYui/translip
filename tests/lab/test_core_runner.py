"""Runner orchestration with a fake invoker + fake scenario (no ML)."""
from __future__ import annotations

from translip_lab.config import LabConfig
from translip_lab.core.invoke import StageResult
from translip_lab.core.runner import run_suite
from translip_lab.core.sample import Sample, SampleManifest
from translip_lab.core.scenario import Scenario


class FakeInvoker:
    def __init__(self):
        self.calls = []

    def translip(self, subcommand, args, *, timeout=None, log_path=None):
        self.calls.append(("translip", subcommand))
        return StageResult(argv=[], returncode=0, stdout="manifest=/x", stderr="",
                           duration_sec=0.0, outputs={"manifest": "/x"})

    def module(self, module, args, *, timeout=None, log_path=None):
        self.calls.append(("module", module))
        return StageResult(argv=[], returncode=0, stdout="", stderr="", duration_sec=0.0, outputs={})


class CountingScenario(Scenario):
    name = "fake"
    primary_metric_key = "cer"
    higher_is_better = False

    def __init__(self):
        self.invocations = 0

    def invoke(self, sample, work_dir, invoker, *, config, timeout, log_path):
        self.invocations += 1
        return invoker.translip("run", ["--input", str(sample.media_path)], log_path=log_path)

    def score(self, sample, work_dir, stage, config):
        return {"cer": 0.1}


def _cfg(tmp_path):
    return LabConfig(
        home=tmp_path, datasets_dir=tmp_path / "d", runs_dir=tmp_path / "runs",
        cache_dir=tmp_path / "cache", translip_cmd=("x",), python_cmd=("y",),
    )


def _manifest(tmp_path):
    media = tmp_path / "a.wav"
    media.write_bytes(b"x")
    return SampleManifest(dataset="t", samples=[Sample(sample_id="s1", media_path=media)])


def test_run_suite_produces_manifest(tmp_path):
    cfg = _cfg(tmp_path)
    man = run_suite(manifest=_manifest(tmp_path), scenarios=[CountingScenario()],
                    suite="suite", invoker=FakeInvoker(), lab_config=cfg, use_cache=False)
    assert man["aggregates"]["fake"]["mean"] == 0.1
    assert man["results"][0]["status"] == "succeeded"
    assert (cfg.runs_dir / man["run_id"] / "run-manifest.json").is_file()


def test_caching_skips_second_invocation(tmp_path):
    cfg = _cfg(tmp_path)
    m = _manifest(tmp_path)
    sc = CountingScenario()
    run_suite(manifest=m, scenarios=[sc], suite="s", invoker=FakeInvoker(),
              lab_config=cfg, use_cache=True, run_id="r1")
    assert sc.invocations == 1
    run_suite(manifest=m, scenarios=[sc], suite="s", invoker=FakeInvoker(),
              lab_config=cfg, use_cache=True, run_id="r2")
    assert sc.invocations == 1  # second run hit the cache → no new invocation


def test_cache_invalidated_by_version_bump(tmp_path):
    cfg = _cfg(tmp_path)
    m = _manifest(tmp_path)
    sc = CountingScenario()
    run_suite(manifest=m, scenarios=[sc], suite="s", invoker=FakeInvoker(),
              lab_config=cfg, use_cache=True, run_id="r1")
    assert sc.invocations == 1
    sc.version = 2  # e.g. the scoring logic changed → cached r1 result must not be reused
    run_suite(manifest=m, scenarios=[sc], suite="s", invoker=FakeInvoker(),
              lab_config=cfg, use_cache=True, run_id="r2")
    assert sc.invocations == 2  # cache miss → re-invoked under the new version


def test_skipped_when_missing_ground_truth(tmp_path):
    cfg = _cfg(tmp_path)

    class NeedsSrt(CountingScenario):
        name = "needs"

        def required_gt(self):
            return ["transcript_srt"]

    sc = NeedsSrt()
    man = run_suite(manifest=_manifest(tmp_path), scenarios=[sc], suite="s",
                    invoker=FakeInvoker(), lab_config=cfg, use_cache=False)
    assert man["results"][0]["status"] == "skipped"
    assert sc.invocations == 0
