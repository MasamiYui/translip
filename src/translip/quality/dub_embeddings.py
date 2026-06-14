"""Enrich a dub-qa report with raw ECAPA-TDNN speaker embeddings.

The dub-qa pipeline normally collapses each segment's speaker embedding into a
single ``speaker_similarity`` scalar (the cosine vs. its reference clip). For
the embedding-scatter visualization we need the underlying 192-dim vectors
themselves, so the UI can run PCA/UMAP-style projections client-side.

This module is intentionally **post-hoc and best-effort**:

* It runs *after* :func:`translip.quality.dub_qa.build_dub_qa` finishes, so it
  never blocks the main report write.
* If the speaker model isn't installed, or any audio file is missing, the
  report is left untouched (or only partially enriched).
* It's idempotent — re-running over an already-enriched report is a no-op for
  segments that already carry an embedding.
* It also exposes a small CLI so existing reports on disk can be backfilled
  without re-running the whole pipeline.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

# Lazy-import the speaker model only inside the function so imports of this
# module remain cheap (and the front-end-only test path doesn't pull torch).
_DEFAULT_DEVICE = "cpu"


def enrich_report_with_embeddings(
    report: dict[str, Any],
    *,
    pipeline_root: Path | str,
    device: str = _DEFAULT_DEVICE,
) -> dict[str, Any]:
    """Add ``speaker_embedding`` to each segment + ``reference_embeddings``.

    Returns the *same* dict (mutated in place) so callers can chain it. Adds
    ``embedding_meta`` describing how many segments were successfully enriched.
    """
    try:
        from ..speaker_embedding import (
            embedding_for_clip,
            load_speechbrain_classifier,
            read_audio_mono,
            resolve_speaker_device,
        )
    except Exception as exc:  # pragma: no cover - environment without torch
        report["embedding_meta"] = {
            "status": "unavailable",
            "reason": f"speaker_embedding import failed: {exc}",
        }
        return report

    root = Path(pipeline_root).expanduser().resolve()
    resolved_device = resolve_speaker_device(device)
    try:
        classifier = load_speechbrain_classifier(resolved_device)
    except Exception as exc:  # pragma: no cover - model download failure
        report["embedding_meta"] = {
            "status": "unavailable",
            "reason": f"speechbrain init failed: {exc}",
        }
        return report

    def _embed(path_value: Any) -> list[float] | None:
        if not path_value:
            return None
        candidate = Path(str(path_value))
        if not candidate.is_absolute():
            candidate = (root / candidate).resolve()
        if not candidate.exists() or not candidate.is_file():
            return None
        try:
            waveform, sr = read_audio_mono(candidate)
            vec = embedding_for_clip(classifier, waveform, sr)
        except Exception:
            return None
        if vec is None:
            return None
        try:
            return [round(float(x), 6) for x in vec]
        except Exception:
            return None

    segments = report.get("segments")
    if not isinstance(segments, list):
        report["embedding_meta"] = {"status": "no_segments"}
        return report

    enriched_count = 0
    skipped_count = 0
    reference_cache: dict[str, list[float]] = {}
    references: dict[str, list[float]] = {}

    for seg in segments:
        if not isinstance(seg, dict):
            continue

        existing = seg.get("speaker_embedding")
        if isinstance(existing, list) and existing:
            enriched_count += 1
        else:
            seg_emb = _embed(seg.get("dub_audio_path"))
            if seg_emb is None:
                skipped_count += 1
            else:
                seg["speaker_embedding"] = seg_emb
                seg["embedding_dim"] = len(seg_emb)
                enriched_count += 1

        reference_path = seg.get("reference_audio_path")
        speaker_id = seg.get("speaker_id") or "—"
        if reference_path and speaker_id not in references:
            cache_key = str(reference_path)
            if cache_key in reference_cache:
                references[speaker_id] = reference_cache[cache_key]
            else:
                ref_emb = _embed(reference_path)
                if ref_emb is not None:
                    reference_cache[cache_key] = ref_emb
                    references[speaker_id] = ref_emb

    report["reference_embeddings"] = references
    report["embedding_meta"] = {
        "status": "ok" if enriched_count else "empty",
        "embedding_dim": _first_dim(segments),
        "enriched_count": enriched_count,
        "skipped_count": skipped_count,
        "reference_count": len(references),
        "device": resolved_device,
        "model": "speechbrain/spkrec-ecapa-voxceleb",
    }
    return report


def _first_dim(segments: list[Any]) -> int | None:
    for seg in segments:
        if isinstance(seg, dict):
            emb = seg.get("speaker_embedding")
            if isinstance(emb, list) and emb:
                return len(emb)
    return None


def enrich_report_path(
    report_path: Path | str,
    *,
    pipeline_root: Path | str,
    device: str = _DEFAULT_DEVICE,
    write: bool = True,
) -> dict[str, Any]:
    """Read a dub-qa report from disk, enrich it, optionally write it back."""
    path = Path(report_path).expanduser().resolve()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"unexpected report shape at {path}")
    enrich_report_with_embeddings(payload, pipeline_root=pipeline_root, device=device)
    if write:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backfill speaker embeddings into a dub-qa report.")
    parser.add_argument("report", type=Path, help="path to dub_qa_report.<lang>.json")
    parser.add_argument(
        "pipeline_root", type=Path, help="task pipeline root (where transcription/b/c/... live)"
    )
    parser.add_argument("--device", default=_DEFAULT_DEVICE, help="speaker model device (cpu / cuda / mps)")
    parser.add_argument("--dry-run", action="store_true", help="don't write, just print summary")
    args = parser.parse_args(argv)

    payload = enrich_report_path(
        args.report,
        pipeline_root=args.pipeline_root,
        device=args.device,
        write=not args.dry_run,
    )
    meta = payload.get("embedding_meta", {})
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())


__all__ = [
    "enrich_report_with_embeddings",
    "enrich_report_path",
]
