from __future__ import annotations

import atexit
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import weakref
from pathlib import Path

import soundfile as sf

from ..config import CACHE_ROOT
from ..exceptions import DependencyError
from .backend import ReferencePackage, SynthSegmentInput, SynthSegmentOutput

_DEFAULT_MODEL_NAME = "OpenMOSS-Team/MOSS-TTS-Nano-100M-ONNX"
_DEFAULT_CLI = "moss-tts-nano"
_DEFAULT_CPU_THREADS = 4
_DEFAULT_MAX_NEW_FRAMES = 375
_DEFAULT_VOICE_CLONE_MAX_TEXT_TOKENS = 75
_DEFAULT_SAMPLE_MODE = "fixed"
_DUBBING_WORKERS_ENV = "TRANSLIP_DUBBING_WORKERS"
_WORKER_SCRIPT = Path(__file__).with_name("_moss_onnx_worker.py")

# Backends with a live worker pool, closed at interpreter exit as a backstop.
# The task-D runner closes its backend explicitly; this only catches leaks.
_LIVE_BACKENDS: "weakref.WeakSet[MossTtsNanoOnnxBackend]" = weakref.WeakSet()


@atexit.register
def _close_live_backends() -> None:  # pragma: no cover - process-teardown safety net
    for backend in list(_LIVE_BACKENDS):
        try:
            backend.close()
        except Exception:
            pass


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _resolve_cli_path() -> str:
    if cli_path := os.environ.get("MOSS_TTS_NANO_CLI"):
        return cli_path
    if cli_path := shutil.which(_DEFAULT_CLI):
        return cli_path
    local_cli = _repo_root() / ".dev-runtime" / "moss-tts-nano-venv" / "bin" / _DEFAULT_CLI
    if local_cli.exists():
        return str(local_cli)
    return _DEFAULT_CLI


def _resolve_python_path(cli_path: str) -> str:
    """Resolve the Python interpreter that owns the MOSS ONNX runtime.

    The persistent worker imports ``onnx_tts_runtime`` from the MOSS virtualenv,
    so we need that env's interpreter — not ``translip``'s. Prefer an explicit
    override, otherwise the ``python`` sitting next to the resolved CLI (both
    live in the venv's ``bin/``), otherwise the current interpreter.
    """

    if python_path := os.environ.get("MOSS_TTS_NANO_PYTHON"):
        return python_path
    sibling = Path(cli_path).with_name("python")
    if sibling.exists():
        return str(sibling)
    return sys.executable


def _persistent_enabled() -> bool:
    value = os.environ.get("MOSS_TTS_NANO_PERSISTENT", "").strip().lower()
    if value in {"0", "false", "no", "off"}:
        return False
    return True


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None or not value.strip():
        return default
    return int(value)


def _resolve_cpu_threads(worker_count_hint: int | None = None) -> int:
    """Pick a CPU thread count that plays well with the dubbing worker pool.

    Honors ``MOSS_TTS_NANO_CPU_THREADS`` when explicitly set. Otherwise, when
    the dubbing runner is configured for parallel synthesis, downscale
    per-process threads so that ``workers * threads`` does not over-subscribe
    CPU cores on Apple Silicon.
    """

    explicit = os.environ.get("MOSS_TTS_NANO_CPU_THREADS")
    if explicit and explicit.strip():
        return max(1, int(explicit))

    # Worker hint comes from an explicit CLI/server request, so it intentionally
    # wins over the legacy TRANSLIP_DUBBING_WORKERS environment override.
    workers = worker_count_hint
    workers_override = os.environ.get(_DUBBING_WORKERS_ENV, "").strip()
    if workers is None and workers_override:
        try:
            workers = max(1, int(workers_override))
        except ValueError:
            workers = 1
    if workers is not None:
        cpu_count = os.cpu_count() or 4
        # Reserve at least 1 thread per process; total threads ~= cpu_count.
        return max(1, min(_DEFAULT_CPU_THREADS, cpu_count // workers))
    return _DEFAULT_CPU_THREADS


class _WorkerDied(RuntimeError):
    """Raised when a persistent worker process can no longer be reached."""


class _MossWorker:
    """One long-lived MOSS ONNX synthesis subprocess with the model preloaded."""

    def __init__(self, *, python_path: str, model_dir: str, cpu_threads: int, max_new_frames: int) -> None:
        command = [
            python_path,
            str(_WORKER_SCRIPT),
            "--onnx-model-dir",
            model_dir,
            "--cpu-threads",
            str(cpu_threads),
            "--max-new-frames",
            str(max_new_frames),
        ]
        try:
            # stderr is inherited so the worker's model-load logs land in the
            # task-D stage log; PIPE-ing it without draining could deadlock.
            self._proc = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
        except FileNotFoundError as exc:
            raise DependencyError(
                "moss-tts-nano is required for the moss-tts-nano-onnx backend. "
                "Install OpenMOSS/MOSS-TTS-Nano and ensure the `moss-tts-nano` CLI is on PATH, "
                "or set MOSS_TTS_NANO_CLI / MOSS_TTS_NANO_PYTHON to its environment."
            ) from exc
        self._lock = threading.Lock()
        self._ready = False

    def wait_ready(self) -> None:
        """Block until the worker reports its model is loaded.

        Spawning (``__init__``) is non-blocking, so a pool can start every
        worker process first and then load all models concurrently rather than
        serializing the (multi-second) model load of each worker.
        """

        if self._ready:
            return
        message = self._read_json()
        if not isinstance(message, dict) or not message.get("ready"):
            detail = (message or {}).get("error") if isinstance(message, dict) else None
            self.close()
            raise DependencyError(
                f"MOSS-TTS-Nano ONNX worker failed to load the model: {detail or 'no ready signal'}"
            )
        self._ready = True

    def _read_json(self) -> dict | None:
        assert self._proc.stdout is not None
        while True:
            line = self._proc.stdout.readline()
            if line == "":
                return None  # EOF: process exited
            line = line.strip()
            if not line:
                continue
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue  # ignore stray stdout noise

    def request(self, payload: dict) -> dict:
        with self._lock:
            if self._proc.poll() is not None:
                raise _WorkerDied("MOSS-TTS-Nano ONNX worker is not running")
            assert self._proc.stdin is not None
            try:
                self._proc.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
                self._proc.stdin.flush()
            except (BrokenPipeError, OSError) as exc:
                raise _WorkerDied(f"failed to send request to MOSS worker: {exc}") from exc
            ack = self._read_json()
            if ack is None:
                raise _WorkerDied("MOSS-TTS-Nano ONNX worker exited mid-request")
            return ack

    def close(self) -> None:
        proc = getattr(self, "_proc", None)
        if proc is None:
            return
        try:
            if proc.stdin is not None:
                proc.stdin.close()
        except Exception:
            pass
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()


class MossTtsNanoOnnxBackend:
    backend_name = "moss-tts-nano-onnx"

    def __init__(self, *, requested_device: str, worker_count_hint: int | None = None) -> None:
        self.requested_device = requested_device
        self.resolved_device = "cpu"
        self.resolved_model = _DEFAULT_MODEL_NAME
        self.cli_path = _resolve_cli_path()
        self.python_path = _resolve_python_path(self.cli_path)
        self.model_dir = os.environ.get("MOSS_TTS_NANO_MODEL_DIR", str(CACHE_ROOT / "models"))
        self.cpu_threads = _resolve_cpu_threads(worker_count_hint=worker_count_hint)
        self.max_new_frames = _env_int("MOSS_TTS_NANO_MAX_NEW_FRAMES", _DEFAULT_MAX_NEW_FRAMES)
        self.voice_clone_max_text_tokens = _env_int(
            "MOSS_TTS_NANO_VOICE_CLONE_MAX_TEXT_TOKENS",
            _DEFAULT_VOICE_CLONE_MAX_TEXT_TOKENS,
        )
        self.sample_mode = os.environ.get("MOSS_TTS_NANO_SAMPLE_MODE", _DEFAULT_SAMPLE_MODE)
        self.persistent = _persistent_enabled()
        self.pool_size = max(1, int(worker_count_hint or 1))
        self._pool: "queue.Queue[_MossWorker] | None" = None
        self._pool_lock = threading.Lock()
        self._workers: list[_MossWorker] = []
        _LIVE_BACKENDS.add(self)

    # -- persistent worker pool ------------------------------------------------

    def _spawn_worker(self) -> _MossWorker:
        return _MossWorker(
            python_path=self.python_path,
            model_dir=self.model_dir,
            cpu_threads=self.cpu_threads,
            max_new_frames=self.max_new_frames,
        )

    def _ensure_pool(self) -> "queue.Queue[_MossWorker]":
        if self._pool is not None:
            return self._pool
        with self._pool_lock:
            if self._pool is not None:
                return self._pool
            pool: "queue.Queue[_MossWorker]" = queue.Queue()
            try:
                # Start every worker process first (non-blocking), then load all
                # models concurrently — serial loads would erase the warm-reuse win.
                workers = [self._spawn_worker() for _ in range(self.pool_size)]
                self._workers.extend(workers)
                for worker in workers:
                    worker.wait_ready()
                    pool.put(worker)
            except Exception:
                for worker in self._workers:
                    worker.close()
                self._workers.clear()
                raise
            self._pool = pool
            return pool

    def _synthesize_persistent(
        self,
        *,
        reference: ReferencePackage,
        segment: SynthSegmentInput,
        output_path: Path,
    ) -> SynthSegmentOutput:
        pool = self._ensure_pool()
        payload = {
            "id": segment.segment_id,
            "text": segment.target_text,
            "prompt_speech": str(reference.prepared_audio_path),
            "output": str(output_path),
            "max_new_frames": self.max_new_frames,
            "voice_clone_max_text_tokens": self.voice_clone_max_text_tokens,
            "sample_mode": self.sample_mode,
        }
        worker = pool.get()
        try:
            try:
                ack = worker.request(payload)
            except _WorkerDied as exc:
                worker.close()
                with self._pool_lock:
                    if worker in self._workers:
                        self._workers.remove(worker)
                    worker = self._spawn_worker()
                    worker.wait_ready()
                    self._workers.append(worker)
                raise RuntimeError(
                    f"MOSS-TTS-Nano ONNX worker died synthesizing {segment.segment_id}: {exc}"
                ) from exc
            if not ack.get("ok"):
                raise RuntimeError(
                    f"MOSS-TTS-Nano ONNX synthesis failed for {segment.segment_id}: {ack.get('error')}"
                )
        finally:
            pool.put(worker)

        if not output_path.exists():
            raise RuntimeError(f"MOSS-TTS-Nano ONNX did not create output audio for {segment.segment_id}")
        return self._build_output(reference=reference, segment=segment, output_path=output_path)

    def close(self) -> None:
        with self._pool_lock:
            for worker in self._workers:
                worker.close()
            self._workers.clear()
            self._pool = None

    # -- shared helpers --------------------------------------------------------

    def _build_output(
        self,
        *,
        reference: ReferencePackage,
        segment: SynthSegmentInput,
        output_path: Path,
    ) -> SynthSegmentOutput:
        info = sf.info(output_path)
        return SynthSegmentOutput(
            segment_id=segment.segment_id,
            audio_path=output_path,
            sample_rate=int(info.samplerate),
            generated_duration_sec=round(float(info.duration), 3),
            backend_metadata={
                "reference_score": reference.score,
                "cpu_threads": self.cpu_threads,
                "max_new_frames": self.max_new_frames,
                "sample_mode": self.sample_mode,
                "persistent": self.persistent,
            },
        )

    def synthesize(
        self,
        *,
        reference: ReferencePackage,
        segment: SynthSegmentInput,
        output_path: Path,
    ) -> SynthSegmentOutput:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if output_path.exists():
            output_path.unlink()
        if self.persistent:
            return self._synthesize_persistent(
                reference=reference,
                segment=segment,
                output_path=output_path,
            )
        return self._synthesize_oneshot(
            reference=reference,
            segment=segment,
            output_path=output_path,
        )

    # -- legacy one-shot subprocess path (MOSS_TTS_NANO_PERSISTENT=0) -----------

    def _synthesize_oneshot(
        self,
        *,
        reference: ReferencePackage,
        segment: SynthSegmentInput,
        output_path: Path,
    ) -> SynthSegmentOutput:
        command = self._build_command(
            reference_audio_path=reference.prepared_audio_path,
            text=segment.target_text,
            output_path=output_path,
        )
        try:
            subprocess.run(command, check=True, capture_output=True, text=True)
        except FileNotFoundError as exc:
            raise DependencyError(
                "moss-tts-nano is required for the moss-tts-nano-onnx backend. "
                "Install OpenMOSS/MOSS-TTS-Nano and ensure the `moss-tts-nano` CLI is on PATH, "
                "or set MOSS_TTS_NANO_CLI to its executable path."
            ) from exc
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or exc.stdout or str(exc)).strip()
            raise RuntimeError(f"MOSS-TTS-Nano ONNX synthesis failed for {segment.segment_id}: {detail}") from exc

        if not output_path.exists():
            raise RuntimeError(f"MOSS-TTS-Nano ONNX did not create output audio for {segment.segment_id}")
        return self._build_output(reference=reference, segment=segment, output_path=output_path)

    def _build_command(self, *, reference_audio_path: Path, text: str, output_path: Path) -> list[str]:
        command = [
            self.cli_path,
            "generate",
            "--backend",
            "onnx",
            "--output",
            str(output_path),
            "--text",
            text,
            "--prompt-speech",
            str(reference_audio_path),
        ]
        if self.model_dir:
            command.extend(["--onnx-model-dir", self.model_dir])
        command.extend(
            [
                "--cpu-threads",
                str(self.cpu_threads),
                "--max-new-frames",
                str(self.max_new_frames),
                "--voice-clone-max-text-tokens",
                str(self.voice_clone_max_text_tokens),
                "--sample-mode",
                self.sample_mode,
            ]
        )
        return command
