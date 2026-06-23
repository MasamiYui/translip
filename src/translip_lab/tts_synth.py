"""Lab-side voice-clone TTS worker (run via ``python -m translip_lab.tts_synth``).

Reuses translip's in-tree Qwen3-TTS voice-clone core *directly* — NOT the server
``atomic_tools`` wrapper, whose ``adapters/__init__`` eager-imports every heavy
adapter (demucs / vision / …) and would violate the lab's "base deps only"
principle. Runs in an isolated subprocess so the multi-GB TTS model is freed on
exit, exactly like the other lab stages and the orchestrator. Prints the
machine-readable ``key=value`` lines the lab ``Invoker`` parses::

    synth_wav=/abs/path/synth.wav
    sample_rate=24000
    tts_backend=qwen3tts

Only ``qwen3tts`` is wired in v1 (the cleanest path: ``model.generate_voice_clone``).
``moss-tts-nano-onnx`` / ``voxcpm2`` need the pipeline's reference-audio
preprocessing (``ReferencePackage``) and a real-model smoke test — see
``docs/translip-lab-tts-clone-eval.zh-CN.md`` §5/§9.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

_QWEN_CLONE_MODEL = "Qwen/Qwen3-TTS-12Hz-0.6B-Base"


def synth_qwen_clone(*, text: str, reference: Path, language: str):
    """Clone ``reference``'s voice saying ``text`` → (waveform, sample_rate).

    Mirrors the atomic TTS tool's ``_generate_voice_clone`` but imports only
    ``translip.dubbing`` core (one-way dependency, no server side-effects).
    """
    from translip.dubbing.backend import SynthSegmentInput, resolve_tts_device
    from translip.dubbing.qwen_tts_backend import (
        _language_name,
        _load_qwen_model,
        _max_new_tokens_for,
        _normalize_waveform,
    )

    device = resolve_tts_device("auto")
    model = _load_qwen_model(_QWEN_CLONE_MODEL, device)
    segment = SynthSegmentInput(
        segment_id="lab-clone", speaker_id="lab", target_lang=language, target_text=text,
        source_duration_sec=max(0.8, len(text) * 0.3), duration_budget_sec=None,
    )
    wavs, sample_rate = model.generate_voice_clone(
        text=text, language=_language_name(language), ref_audio=str(reference),
        x_vector_only_mode=True, non_streaming_mode=True,
        max_new_tokens=_max_new_tokens_for(segment),
    )
    if not wavs:
        raise RuntimeError("Qwen3-TTS returned no waveform for voice clone")
    return _normalize_waveform(wavs[0]), int(sample_rate)


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="lab voice-clone TTS worker")
    ap.add_argument("--text", required=True)
    ap.add_argument("--reference", required=True, help="reference voice wav to clone")
    ap.add_argument("--output", required=True)
    ap.add_argument("--language", default="zh")
    ap.add_argument("--backend", default="qwen3tts")
    args = ap.parse_args(argv)

    if args.backend != "qwen3tts":
        raise SystemExit(
            f"tts_synth v1 only supports qwen3tts; got {args.backend!r} "
            "(moss/voxcpm2 wiring is a documented follow-up)"
        )

    import soundfile as sf

    waveform, sample_rate = synth_qwen_clone(
        text=args.text, reference=Path(args.reference), language=args.language)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    sf.write(out, waveform, sample_rate)
    print(f"synth_wav={out}")
    print(f"sample_rate={sample_rate}")
    print(f"tts_backend={args.backend}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
