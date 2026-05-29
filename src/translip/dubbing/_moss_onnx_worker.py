"""Persistent MOSS-TTS-Nano ONNX synthesis worker.

This script is **not** part of the ``translip`` package runtime — it is executed
by the *MOSS* virtualenv's Python interpreter (the same env that ships the
``moss-tts-nano`` CLI), because the MOSS ONNX runtime lives in its own venv with
its own dependencies. :class:`translip.dubbing.moss_tts_nano_backend.MossTtsNanoOnnxBackend`
spawns one or more of these workers and keeps them alive for the whole task-D
run, so the ONNX model + audio tokenizer are loaded **once** instead of being
cold-started for every segment.

Protocol (newline-delimited JSON over stdin/stdout):

* On startup the worker loads the model and prints a single line
  ``{"ready": true}`` (or ``{"ready": false, "error": "..."}`` then exits 1).
* For each request line ``{"id", "text", "prompt_speech", "output",
  "max_new_frames", "voice_clone_max_text_tokens", "sample_mode"}`` it
  synthesizes one clip to ``output`` and prints one ack line
  ``{"id", "ok": true, "audio_path", "sample_rate"}`` or
  ``{"id", "ok": false, "error": "..."}``.
* A per-request error never terminates the worker; it keeps serving until EOF.

Fidelity: the call mirrors the one-shot ``moss-tts-nano generate --backend onnx``
path (``enable_wetext=False, enable_normalize_tts_text=True``) and resets the RNG
to ``default_rng(1234)`` before every request so output matches a fresh process.
"""

from __future__ import annotations

import argparse
import json
import sys

# Default sampling seed used by the MOSS ONNX runtime constructor. Resetting the
# RNG to this value before each request reproduces the deterministic output of a
# fresh one-shot CLI process (which starts every run from this same seed).
_RNG_SEED = 1234


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Persistent MOSS ONNX synthesis worker.")
    parser.add_argument("--onnx-model-dir", default=None)
    parser.add_argument("--cpu-threads", type=int, default=4)
    parser.add_argument("--max-new-frames", type=int, default=375)
    return parser.parse_args(argv)


def _emit(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)

    try:
        from onnx_tts_runtime import OnnxTtsRuntime

        runtime = OnnxTtsRuntime(
            model_dir=args.onnx_model_dir,
            thread_count=max(1, int(args.cpu_threads)),
            max_new_frames=int(args.max_new_frames),
            do_sample=True,
            sample_mode="fixed",
        )
    except Exception as exc:  # pragma: no cover - exercised only with the real model
        _emit({"ready": False, "error": f"{type(exc).__name__}: {exc}"})
        return 1

    _emit({"ready": True})

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        request_id = None
        try:
            request = json.loads(line)
            request_id = request.get("id")
            result = runtime.synthesize(
                text=str(request.get("text") or ""),
                voice=None,
                prompt_audio_path=request["prompt_speech"],
                output_audio_path=request["output"],
                sample_mode=str(request.get("sample_mode") or "fixed"),
                do_sample=True,
                streaming=False,
                max_new_frames=int(request.get("max_new_frames") or args.max_new_frames),
                voice_clone_max_text_tokens=int(request.get("voice_clone_max_text_tokens") or 75),
                enable_wetext=False,
                enable_normalize_tts_text=True,
                seed=_RNG_SEED,
            )
            _emit(
                {
                    "id": request_id,
                    "ok": True,
                    "audio_path": str(result["audio_path"]),
                    "sample_rate": int(result["sample_rate"]),
                }
            )
        except Exception as exc:  # pragma: no cover - exercised only with the real model
            _emit({"id": request_id, "ok": False, "error": f"{type(exc).__name__}: {exc}"})

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
