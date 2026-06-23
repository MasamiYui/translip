"""JobManager lifecycle — real subprocesses (python -c), no ML, fully offline."""
from __future__ import annotations

import json
import sys
import time

from translip_lab.server.jobs import Job, JobManager


def _wait(jm: JobManager, job_id: str, timeout: float = 15.0) -> Job:
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = jm.get_job(job_id)
        if job and job.status in ("succeeded", "failed"):
            return job
        time.sleep(0.02)
    raise AssertionError(f"job {job_id} did not finish in {timeout}s")


def _writes_manifest_cmd(run_dir) -> list[str]:
    code = (
        "import pathlib,sys;"
        "d=pathlib.Path(sys.argv[1]);d.mkdir(parents=True,exist_ok=True);"
        "(d/'run-manifest.json').write_text('{}')"
    )
    return [sys.executable, "-c", code, str(run_dir)]


def test_job_succeeds_when_manifest_produced(tmp_path):
    jm = JobManager(runs_dir=tmp_path / "runs")
    jm.submit(cmd=_writes_manifest_cmd(tmp_path / "runs" / "t1"), job_id="t1", suite="s")
    job = _wait(jm, "t1")
    assert job.status == "succeeded"
    assert job.run_id == "t1" and job.returncode == 0
    assert job.started_at and job.finished_at


def test_job_fails_without_manifest(tmp_path):
    jm = JobManager(runs_dir=tmp_path / "runs")
    jm.submit(cmd=[sys.executable, "-c", "import sys; sys.exit(2)"], job_id="t2")
    job = _wait(jm, "t2")
    assert job.status == "failed" and job.returncode == 2 and job.run_id is None
    assert "no run-manifest" in (job.error or "")


def test_log_is_captured(tmp_path):
    jm = JobManager(runs_dir=tmp_path / "runs")
    jm.submit(cmd=[sys.executable, "-c", "print('HELLO-LAB-LOG')"], job_id="t3")
    _wait(jm, "t3")
    assert "HELLO-LAB-LOG" in jm.tail_log("t3")


def test_jobs_run_serially(tmp_path):
    jm = JobManager(runs_dir=tmp_path / "runs")
    marks = tmp_path / "marks"
    marks.mkdir()
    code = (
        "import time,pathlib,sys;"
        "p=pathlib.Path(sys.argv[1]);"
        "p.write_text(str(time.time()));"
        "time.sleep(0.4);"
        "p.write_text(p.read_text()+' '+str(time.time()))"
    )
    jm.submit(cmd=[sys.executable, "-c", code, str(marks / "a")], job_id="a")
    jm.submit(cmd=[sys.executable, "-c", code, str(marks / "b")], job_id="b")
    _wait(jm, "a")
    _wait(jm, "b")
    a_start, a_end = (float(x) for x in (marks / "a").read_text().split())
    b_start, b_end = (float(x) for x in (marks / "b").read_text().split())
    first_end, second_start = (a_end, b_start) if a_start < b_start else (b_end, a_start)
    assert first_end <= second_start + 0.1  # single worker → active windows don't overlap


def test_list_and_get(tmp_path):
    jm = JobManager(runs_dir=tmp_path / "runs")
    jm.submit(cmd=[sys.executable, "-c", "pass"], job_id="z1", suite="s1")
    _wait(jm, "z1")
    assert any(j["job_id"] == "z1" for j in jm.list_jobs())
    assert jm.get_job("z1").suite == "s1"
    assert jm.get_job("missing") is None


def test_orphan_jobs_marked_failed_on_reload(tmp_path):
    runs = tmp_path / "runs"
    (runs / ".jobs").mkdir(parents=True)
    (runs / ".jobs" / "stale.json").write_text(json.dumps({
        "job_id": "stale", "cmd": [], "status": "running", "created_at": "2026-01-01T00:00:00",
    }), encoding="utf-8")
    jm = JobManager(runs_dir=runs)  # reload picks up the orphan
    stale = jm.get_job("stale")
    assert stale is not None and stale.status == "failed" and "interrupted" in (stale.error or "")
