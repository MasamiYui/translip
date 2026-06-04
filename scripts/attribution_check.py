#!/usr/bin/env python3
"""Cross-speaker voiceprint attribution check.

Dub QA compares each generated clip to *its own* reference, so a line dubbed in
the WRONG voice (diarization put it in the wrong speaker cluster) scores as a
perfect pass — the defect is structurally invisible. This tool closes that blind
spot: it embeds each ORIGINAL segment's audio and compares it to EVERY speaker's
prototype, flagging segments whose assigned speaker is not the best (or near-best)
acoustic match.

Usage:
  python scripts/attribution_check.py <pipeline_root> [--margin 0.06] [--json out.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from translip.speaker_embedding import (  # noqa: E402
    embedding_for_clip,
    extract_audio_clip,
    load_speechbrain_classifier,
    normalize_embedding,
    read_audio_mono,
    resolve_speaker_device,
)


def _glob1(root: Path, pattern: str) -> Path | None:
    hits = sorted(root.glob(pattern))
    return hits[0] if hits else None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--margin", type=float, default=0.06,
                    help="flag a segment when another speaker beats the assigned one by this cosine margin")
    ap.add_argument("--json", dest="json_out")
    args = ap.parse_args()
    root = Path(args.root)

    profiles_path = _glob1(root, "task-b/**/speaker_profiles.json")
    segments_path = (_glob1(root, "asr-ocr-correct/**/segments.zh.corrected.json")
                     or _glob1(root, "task-a/**/segments.zh.json"))
    voice_path = (_glob1(root, "stage1/**/voice.wav") or _glob1(root, "stage1/**/voice.mp3")
                  or _glob1(root, "stage1/**/voice.*"))
    if not (profiles_path and segments_path and voice_path):
        print(f"missing inputs: profiles={profiles_path} segments={segments_path} voice={voice_path}")
        sys.exit(1)

    profiles = json.loads(profiles_path.read_text())["profiles"]
    label_to_sid, protos = {}, {}
    for p in profiles:
        emb = p.get("prototype_embedding")
        if emb:
            sid = p["speaker_id"]
            protos[sid] = normalize_embedding(np.asarray(emb, dtype=np.float32))
            label_to_sid[str(p.get("source_label"))] = sid
    proto_ids = list(protos)
    proto_mat = np.stack([protos[s] for s in proto_ids]) if proto_ids else np.zeros((0, 192))

    segs = json.loads(segments_path.read_text())
    rows = segs.get("segments") if isinstance(segs, dict) else segs

    device = resolve_speaker_device("auto")
    classifier = load_speechbrain_classifier(device)
    waveform, sr = read_audio_mono(voice_path)

    results, suspects = [], []
    for seg in rows:
        sid_assigned = label_to_sid.get(str(seg.get("speaker_label")))
        start = float(seg.get("start", 0.0)); end = float(seg.get("end", 0.0))
        if sid_assigned is None or end - start < 0.4 or not proto_ids:
            continue
        clip = extract_audio_clip(waveform, sr, start=start, end=end)
        emb = embedding_for_clip(classifier, clip, sr)
        if emb is None:
            continue
        cos = proto_mat @ emb  # cosine (all unit-normalized)
        order = np.argsort(cos)[::-1]
        best_sid = proto_ids[order[0]]
        assigned_cos = float(cos[proto_ids.index(sid_assigned)])
        best_cos = float(cos[order[0]])
        second_cos = float(cos[order[1]]) if len(order) > 1 else -1.0
        rivals = [float(c) for s, c in zip(proto_ids, cos) if s != sid_assigned]
        confidence = float(assigned_cos - max(rivals)) if rivals else 1.0
        row = {
            "segment_id": seg.get("id") or seg.get("segment_id"),
            "assigned": sid_assigned, "assigned_cos": round(assigned_cos, 3),
            "best": best_sid, "best_cos": round(best_cos, 3),
            "confidence": round(confidence, 3),
            "text": (seg.get("text") or "")[:24],
        }
        results.append(row)
        if best_sid != sid_assigned and (best_cos - assigned_cos) > args.margin:
            suspects.append(row)

    print(f"\n{'='*70}\n  ATTRIBUTION CHECK — {root.name}\n{'='*70}")
    print(f"  speakers: {proto_ids}")
    print(f"  segments checked: {len(results)}   SUSPECTED MIS-ATTRIBUTION: {len(suspects)}")
    conf = [r["confidence"] for r in results]
    if conf:
        print(f"  attribution confidence (assigned − best-rival cosine): "
              f"median {np.median(conf):+.3f}  min {min(conf):+.3f}")
    if suspects:
        print("  ── suspects (assigned voice is NOT the best acoustic match) ──")
        for r in suspects:
            print(f"     {r['segment_id']}: assigned {r['assigned']}({r['assigned_cos']}) "
                  f"but {r['best']}({r['best_cos']}) matches better  text={r['text']!r}")
    else:
        print("  no mis-attribution suspects above margin.")
    print("=" * 70)
    if args.json_out:
        Path(args.json_out).write_text(json.dumps({"results": results, "suspects": suspects}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
