"""Registry of TTS (dubbing) backends.

Adding a TTS backend is a single registration here: provide a factory that
lazily imports and constructs the implementation. Lazy imports keep heavy TTS
runtimes (torch/onnx/voxcpm) off the import path until the backend is used.

Factories take explicit keyword args (``device``, ``worker_count_hint``) rather
than a whole ``DubbingRequest`` so that *every* call site — the dubbing runner,
the repair executor, atomic-tool adapters and the editor route — can dispatch
through the same registry instead of re-implementing the ``if/elif`` chain.

Capability facts that used to live as ``if backend_name == ...`` helpers are
attached here as :class:`~translip.registry.BackendInfo` metadata:

* ``supports_parallel_workers`` — only MOSS scales across worker processes, so
  the runner reads this instead of string-matching the backend name.
* ``supports_reference_retry`` — VoxCPM2 benefits from retrying alternate
  reference clips on weak output.
"""

from __future__ import annotations

from ..registry import BackendRegistry

TTS_BACKENDS: BackendRegistry = BackendRegistry("dubbing")


@TTS_BACKENDS.register(
    "moss-tts-nano-onnx",
    summary="MOSS-TTS-Nano via ONNX runtime (default).",
    requires_reference_audio=True,
    metadata={"supports_parallel_workers": True},
)
def _build_moss(*, device: str = "auto", worker_count_hint: int | None = None):
    from .moss_tts_nano_backend import MossTtsNanoOnnxBackend

    return MossTtsNanoOnnxBackend(requested_device=device, worker_count_hint=worker_count_hint)


@TTS_BACKENDS.register(
    "qwen3tts",
    summary="Qwen3-TTS voice cloning.",
    requires_reference_audio=True,
)
def _build_qwen(*, device: str = "auto", worker_count_hint: int | None = None):
    from .qwen_tts_backend import QwenTTSBackend

    return QwenTTSBackend(requested_device=device)


@TTS_BACKENDS.register(
    "voxcpm2",
    summary="VoxCPM2 voice cloning.",
    requires_reference_audio=True,
    metadata={"supports_reference_retry": True},
)
def _build_voxcpm(*, device: str = "auto", worker_count_hint: int | None = None):
    from .voxcpm_tts_backend import VoxCPMTTSBackend

    return VoxCPMTTSBackend(requested_device=device)


__all__ = ["TTS_BACKENDS"]
