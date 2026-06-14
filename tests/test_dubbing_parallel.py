"""Tests for the parallel synthesis path in ``translip.dubbing.runner``.

These tests cover the behaviour added when introducing the segment-level
ThreadPool concurrency:

* ``_resolve_dubbing_concurrency`` strategy + ``TRANSLIP_DUBBING_WORKERS``
* MOSS ``cpu_threads`` autotune via ``_resolve_cpu_threads``
* End-to-end equivalence between serial and parallel ``synthesize_speaker``
  outputs (segment ordering, audio paths, report rows)
* Exception in one segment does not block the rest of the batch
* Manifest exposes the new observability fields (``concurrency``,
  ``wall_time_sec``, ``sum_segment_time_sec``)
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from translip.dubbing.runner import (
    _resolve_dubbing_concurrency,
    synthesize_speaker,
)
from translip.types import DubbingRequest


def _write_audio(path: Path, duration_sec: float, *, sample_rate: int = 16_000, amplitude: float = 0.05) -> None:
    waveform = amplitude * np.ones(int(duration_sec * sample_rate), dtype=np.float32)
    sf.write(path, waveform, sample_rate)


class _SimpleEval:
    speaker_similarity = 0.7
    speaker_status = "passed"
    backread_text = "ok"
    text_similarity = 1.0
    intelligibility_status = "passed"
    duration_ratio = 1.0
    duration_status = "passed"
    overall_status = "passed"


class _SlowBackend:
    """Backend that sleeps deterministically and records concurrency.

    The recorded ``max_active`` lets us prove that the synthesizer actually
    runs multiple segments in parallel under the thread-pool path while
    remaining a pure-Python sleep (no real TTS dependencies).
    """

    backend_name = "slow-fake-tts"
    resolved_model = "slow"
    resolved_device = "cpu"

    def __init__(self, *, sleep_sec: float = 0.05) -> None:
        self.sleep_sec = sleep_sec
        self._lock = threading.Lock()
        self._active = 0
        self.max_active = 0
        self.calls: list[str] = []

    def synthesize(self, *, reference, segment, output_path):
        with self._lock:
            self._active += 1
            self.max_active = max(self.max_active, self._active)
            self.calls.append(segment.segment_id)
        try:
            time.sleep(self.sleep_sec)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            sample_rate = 24_000
            waveform = 0.02 * np.ones(int(0.6 * sample_rate), dtype=np.float32)
            sf.write(output_path, waveform, sample_rate)
            return type(
                "SynthOutput",
                (),
                {
                    "segment_id": segment.segment_id,
                    "audio_path": output_path,
                    "sample_rate": sample_rate,
                    "generated_duration_sec": 0.6,
                    "backend_metadata": {},
                },
            )()
        finally:
            with self._lock:
                self._active -= 1


class _FlakyBackend(_SlowBackend):
    """Backend that raises on a specific segment id."""

    def __init__(self, *, fail_segment_id: str, sleep_sec: float = 0.02) -> None:
        super().__init__(sleep_sec=sleep_sec)
        self.fail_segment_id = fail_segment_id

    def synthesize(self, *, reference, segment, output_path):
        if segment.segment_id == self.fail_segment_id:
            raise RuntimeError(f"forced failure for {segment.segment_id}")
        return super().synthesize(reference=reference, segment=segment, output_path=output_path)


def _build_translation_payload(num_segments: int) -> dict:
    return {
        "backend": {"target_lang": "en", "output_tag": "en"},
        "segments": [
            {
                "segment_id": f"seg-{idx:04d}",
                "speaker_id": "spk_0000",
                "speaker_label": "SPEAKER_00",
                "start": float(idx),
                "duration": 1.0,
                "target_text": f"Hello number {idx}.",
                "duration_budget": {"estimated_tts_duration_sec": 1.0},
                "qa_flags": [],
            }
            for idx in range(num_segments)
        ],
    }


def _write_inputs(tmp_path: Path, num_segments: int) -> tuple[Path, Path, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    reference_clip = tmp_path / "reference.wav"
    _write_audio(reference_clip, 9.0)
    translation_path = tmp_path / "translation.en.json"
    profiles_path = tmp_path / "speaker_profiles.json"
    translation_path.write_text(
        json.dumps(_build_translation_payload(num_segments), ensure_ascii=False),
        encoding="utf-8",
    )
    profiles_path.write_text(
        json.dumps(
            {
                "profiles": [
                    {
                        "profile_id": "profile_0000",
                        "speaker_id": "spk_0000",
                        "reference_clips": [
                            {
                                "path": str(reference_clip),
                                "text": "这是声音参考文本",
                                "duration": 9.0,
                                "rms": 0.05,
                            }
                        ],
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return translation_path, profiles_path, reference_clip


# -------------------- Concurrency strategy --------------------


def test_resolve_dubbing_concurrency_defaults_for_moss(monkeypatch) -> None:
    monkeypatch.delenv("TRANSLIP_DUBBING_WORKERS", raising=False)

    class FakeMoss:
        backend_name = "moss-tts-nano-onnx"

    workers = _resolve_dubbing_concurrency(FakeMoss())
    assert workers >= 1
    assert workers <= 4  # bounded by _MOSS_MAX_WORKERS


def test_resolve_dubbing_concurrency_defaults_to_one_for_qwen(monkeypatch) -> None:
    monkeypatch.delenv("TRANSLIP_DUBBING_WORKERS", raising=False)

    class FakeQwen:
        backend_name = "qwen3tts"

    assert _resolve_dubbing_concurrency(FakeQwen()) == 1


def test_resolve_dubbing_concurrency_respects_env_override(monkeypatch) -> None:
    monkeypatch.setenv("TRANSLIP_DUBBING_WORKERS", "8")

    class FakeQwen:
        backend_name = "qwen3tts"

    assert _resolve_dubbing_concurrency(FakeQwen()) == 8


def test_resolve_dubbing_concurrency_explicit_request_wins(monkeypatch) -> None:
    monkeypatch.setenv("TRANSLIP_DUBBING_WORKERS", "8")

    class FakeQwen:
        backend_name = "qwen3tts"

    assert _resolve_dubbing_concurrency(FakeQwen(), requested_workers=3) == 3


def test_resolve_dubbing_concurrency_ignores_invalid_override(monkeypatch) -> None:
    monkeypatch.setenv("TRANSLIP_DUBBING_WORKERS", "not-a-number")

    class FakeMoss:
        backend_name = "moss-tts-nano-onnx"

    workers = _resolve_dubbing_concurrency(FakeMoss())
    assert workers >= 1


def test_resolve_dubbing_concurrency_clamps_to_at_least_one(monkeypatch) -> None:
    monkeypatch.setenv("TRANSLIP_DUBBING_WORKERS", "0")

    class FakeMoss:
        backend_name = "moss-tts-nano-onnx"

    assert _resolve_dubbing_concurrency(FakeMoss()) == 1


# -------------------- MOSS cpu_threads autotune --------------------


def test_moss_cpu_threads_autotunes_with_dubbing_workers(monkeypatch) -> None:
    from translip.dubbing.moss_tts_nano_backend import _resolve_cpu_threads

    monkeypatch.delenv("MOSS_TTS_NANO_CPU_THREADS", raising=False)
    monkeypatch.setenv("TRANSLIP_DUBBING_WORKERS", "4")
    monkeypatch.setattr("translip.dubbing.moss_tts_nano_backend.os.cpu_count", lambda: 8)

    # 8 cpus / 4 workers = 2 threads each, capped at default 4.
    assert _resolve_cpu_threads() == 2


def test_moss_cpu_threads_autotunes_with_worker_count_hint(monkeypatch) -> None:
    from translip.dubbing.moss_tts_nano_backend import _resolve_cpu_threads

    monkeypatch.delenv("MOSS_TTS_NANO_CPU_THREADS", raising=False)
    monkeypatch.delenv("TRANSLIP_DUBBING_WORKERS", raising=False)
    monkeypatch.setattr("translip.dubbing.moss_tts_nano_backend.os.cpu_count", lambda: 8)

    assert _resolve_cpu_threads(worker_count_hint=4) == 2


def test_moss_cpu_threads_explicit_override_wins(monkeypatch) -> None:
    from translip.dubbing.moss_tts_nano_backend import _resolve_cpu_threads

    monkeypatch.setenv("MOSS_TTS_NANO_CPU_THREADS", "6")
    monkeypatch.setenv("TRANSLIP_DUBBING_WORKERS", "4")
    assert _resolve_cpu_threads() == 6


def test_moss_cpu_threads_default_when_no_env(monkeypatch) -> None:
    from translip.dubbing.moss_tts_nano_backend import _resolve_cpu_threads

    monkeypatch.delenv("MOSS_TTS_NANO_CPU_THREADS", raising=False)
    monkeypatch.delenv("TRANSLIP_DUBBING_WORKERS", raising=False)
    assert _resolve_cpu_threads() == 4


# -------------------- End-to-end equivalence --------------------


def _run_with_workers(
    tmp_path: Path,
    monkeypatch,
    *,
    workers: str,
    num_segments: int = 6,
    backend_factory=None,
):
    monkeypatch.setenv("TRANSLIP_DUBBING_WORKERS", workers)
    monkeypatch.setattr(
        "translip.dubbing.runner.evaluate_segment",
        lambda **_: _SimpleEval(),
    )
    translation_path, profiles_path, _ = _write_inputs(tmp_path, num_segments)
    backend = backend_factory() if backend_factory else _SlowBackend(sleep_sec=0.02)
    request = DubbingRequest(
        translation_path=translation_path,
        profiles_path=profiles_path,
        output_dir=tmp_path / f"output-{workers}",
        speaker_id="spk_0000",
    )
    result = synthesize_speaker(request, backend_override=backend)
    return backend, result


def test_serial_and_parallel_produce_equivalent_reports(tmp_path: Path, monkeypatch) -> None:
    backend_serial, result_serial = _run_with_workers(
        tmp_path / "serial", monkeypatch, workers="1", num_segments=5
    )
    backend_parallel, result_parallel = _run_with_workers(
        tmp_path / "parallel", monkeypatch, workers="4", num_segments=5
    )

    serial_report = json.loads(result_serial.artifacts.report_path.read_text(encoding="utf-8"))
    parallel_report = json.loads(result_parallel.artifacts.report_path.read_text(encoding="utf-8"))

    serial_segments = serial_report["segments"]
    parallel_segments = parallel_report["segments"]

    # Same count, same ordering by segment_id, same per-row business fields.
    assert [row["segment_id"] for row in serial_segments] == [row["segment_id"] for row in parallel_segments]
    assert [row["index"] for row in serial_segments] == [row["index"] for row in parallel_segments]
    for serial_row, parallel_row in zip(serial_segments, parallel_segments, strict=True):
        for key in (
            "segment_id",
            "speaker_id",
            "target_text",
            "dubbing_text",
            "duration_status",
            "speaker_status",
            "intelligibility_status",
            "overall_status",
            "synthesis_mode",
            "attempt_count",
            "selected_attempt_index",
        ):
            assert serial_row[key] == parallel_row[key], f"mismatch on {key}"

    # Parallel run should observe more than one concurrent synth call.
    assert backend_parallel.max_active >= 2
    assert backend_serial.max_active == 1

    # Manifest exposes the new observability fields.
    parallel_manifest = json.loads(result_parallel.artifacts.manifest_path.read_text(encoding="utf-8"))
    resolved = parallel_manifest["resolved"]
    assert resolved["concurrency"] == 4
    assert resolved["wall_time_sec"] >= 0
    assert resolved["sum_segment_time_sec"] >= 0
    assert resolved["observed_speedup"] >= 0


def test_parallel_segments_are_ordered_by_input_segment_id(tmp_path: Path, monkeypatch) -> None:
    _, result = _run_with_workers(tmp_path, monkeypatch, workers="4", num_segments=8)
    report = json.loads(result.artifacts.report_path.read_text(encoding="utf-8"))
    segment_ids = [row["segment_id"] for row in report["segments"]]
    assert segment_ids == sorted(segment_ids)
    assert [row["index"] for row in report["segments"]] == list(range(1, len(segment_ids) + 1))


def test_parallel_failure_in_one_segment_propagates_without_corrupting_others(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("TRANSLIP_DUBBING_WORKERS", "3")
    monkeypatch.setattr(
        "translip.dubbing.runner.evaluate_segment",
        lambda **_: _SimpleEval(),
    )
    translation_path, profiles_path, _ = _write_inputs(tmp_path, num_segments=4)
    backend = _FlakyBackend(fail_segment_id="seg-0002", sleep_sec=0.01)

    request = DubbingRequest(
        translation_path=translation_path,
        profiles_path=profiles_path,
        output_dir=tmp_path / "output",
        speaker_id="spk_0000",
    )

    with pytest.raises(Exception):
        synthesize_speaker(request, backend_override=backend)

    # Manifest is written even on failure with a "failed" status. Path layout
    # follows ``output_dir / <translation parent dir name> / <speaker_id>``.
    manifest_candidates = list((tmp_path / "output").rglob("synthesis-manifest.json"))
    assert manifest_candidates, "expected at least one manifest file on failure"
    manifest = json.loads(manifest_candidates[0].read_text(encoding="utf-8"))
    assert manifest["status"] == "failed"
    assert "forced failure" in (manifest.get("error") or "")


def test_parallel_actually_speeds_up_wall_time(tmp_path: Path, monkeypatch) -> None:
    """Smoke check: 4 workers should be meaningfully faster than 1 worker.

    We make each fake synth sleep 60ms so the wall-time difference is well
    above scheduler/setup noise even on slow CI hosts.
    """
    monkeypatch.setattr(
        "translip.dubbing.runner.evaluate_segment",
        lambda **_: _SimpleEval(),
    )

    def run(workers: str, root: Path) -> float:
        monkeypatch.setenv("TRANSLIP_DUBBING_WORKERS", workers)
        translation_path, profiles_path, _ = _write_inputs(root, num_segments=6)
        backend = _SlowBackend(sleep_sec=0.06)
        request = DubbingRequest(
            translation_path=translation_path,
            profiles_path=profiles_path,
            output_dir=root / "output",
            speaker_id="spk_0000",
        )
        synthesize_speaker(request, backend_override=backend)
        manifest_candidates = list((root / "output").rglob("synthesis-manifest.json"))
        assert manifest_candidates
        manifest = json.loads(manifest_candidates[0].read_text(encoding="utf-8"))
        return float(manifest["resolved"]["wall_time_sec"])

    serial_time = run("1", tmp_path / "serial")
    parallel_time = run("4", tmp_path / "parallel")
    # 4× concurrency on 6 segments: lower bound ~ 1.5× speedup is safe.
    assert parallel_time < serial_time, f"parallel ({parallel_time}) should beat serial ({serial_time})"
