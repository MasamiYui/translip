from __future__ import annotations

from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient


class FakeProbeAdapter:
    def validate_params(self, params: dict) -> dict:
        return dict(params)

    def run(self, params: dict, input_dir: Path, output_dir: Path, on_progress) -> dict:
        input_file = next(path for path in input_dir.rglob("*") if path.is_file())
        on_progress(50.0, "probing")
        report = output_dir / "probe.json"
        report.write_text(
            '{"format_name":"mp4","duration_sec":12.3,"has_video":true,"has_audio":true}',
            encoding="utf-8",
        )
        return {
            "path": input_file.name,
            "format_name": "mp4",
            "duration_sec": 12.3,
            "has_video": True,
            "has_audio": True,
            "report_file": "probe.json",
        }


def test_atomic_tools_api_supports_upload_run_status_and_artifacts(tmp_path: Path, monkeypatch) -> None:
    import translip.server.atomic_tools as atomic_tools  # noqa: F401
    from translip.server.app import app
    from translip.server.atomic_tools.job_manager import JobManager
    from translip.server.routes import atomic_tools as atomic_tools_route

    manager = JobManager(root=tmp_path / "atomic-tools")
    manager.register_adapter("probe", FakeProbeAdapter())
    monkeypatch.setattr(atomic_tools_route, "job_manager", manager)

    client = TestClient(app)

    tools_response = client.get("/api/atomic-tools/tools")
    assert tools_response.status_code == 200
    assert {tool["tool_id"] for tool in tools_response.json()} == {
        "separation",
        "mixing",
        "transcription",
        "transcript-correction",
        "translation",
        "tts",
        "probe",
        "muxing",
    }

    upload_response = client.post(
        "/api/atomic-tools/upload",
        files={"file": ("demo.mp4", BytesIO(b"video bytes"), "video/mp4")},
    )
    assert upload_response.status_code == 200
    file_id = upload_response.json()["file_id"]

    run_response = client.post("/api/atomic-tools/probe/run", json={"file_id": file_id})
    assert run_response.status_code == 200
    job_id = run_response.json()["job_id"]

    status_response = client.get(f"/api/atomic-tools/probe/jobs/{job_id}")
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "completed"
    assert status_response.json()["result"]["report_file"] == "probe.json"

    result_response = client.get(f"/api/atomic-tools/probe/jobs/{job_id}/result")
    assert result_response.status_code == 200
    assert result_response.json()["report_file"] == "probe.json"

    artifacts_response = client.get(f"/api/atomic-tools/probe/jobs/{job_id}/artifacts")
    assert artifacts_response.status_code == 200
    artifacts = artifacts_response.json()
    assert [artifact["filename"] for artifact in artifacts] == ["probe.json"]
    assert artifacts[0]["file_id"]

    download_response = client.get(
        f"/api/atomic-tools/probe/jobs/{job_id}/artifacts/probe.json"
    )
    assert download_response.status_code == 200
    assert download_response.json()["format_name"] == "mp4"


def test_atomic_tools_api_returns_404_for_missing_or_mismatched_jobs(
    tmp_path: Path, monkeypatch
) -> None:
    import translip.server.atomic_tools as atomic_tools  # noqa: F401
    from translip.server.app import app
    from translip.server.atomic_tools.job_manager import JobManager
    from translip.server.routes import atomic_tools as atomic_tools_route

    manager = JobManager(root=tmp_path / "atomic-tools")
    manager.register_adapter("probe", FakeProbeAdapter())
    monkeypatch.setattr(atomic_tools_route, "job_manager", manager)

    client = TestClient(app)

    missing_job_id = "does-not-exist"
    status_response = client.get(f"/api/atomic-tools/probe/jobs/{missing_job_id}")
    assert status_response.status_code == 404
    assert status_response.json()["detail"] == "Job not found"

    artifacts_response = client.get(f"/api/atomic-tools/probe/jobs/{missing_job_id}/artifacts")
    assert artifacts_response.status_code == 404
    assert artifacts_response.json()["detail"] == "Job not found"

    result_response = client.get(f"/api/atomic-tools/probe/jobs/{missing_job_id}/result")
    assert result_response.status_code == 404
    assert result_response.json()["detail"] == "Job not found"

    upload_response = client.post(
        "/api/atomic-tools/upload",
        files={"file": ("demo.mp4", BytesIO(b"video bytes"), "video/mp4")},
    )
    file_id = upload_response.json()["file_id"]
    run_response = client.post("/api/atomic-tools/probe/run", json={"file_id": file_id})
    job_id = run_response.json()["job_id"]

    mismatch_response = client.get(f"/api/atomic-tools/tts/jobs/{job_id}")
    assert mismatch_response.status_code == 404
    assert mismatch_response.json()["detail"] == "Job not found"
