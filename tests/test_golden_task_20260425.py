"""Golden regression test for the task-20260425-023015 failure modes.

Historical background
---------------------
task-20260425-023015 exhibited three catastrophic symptoms:

1. **spk_0002 fully dropped**: all 6 segments had duration in [8.9, 34.9] s so
   ``is_usable_task_d_segment`` (hard 1.0-6.0 filter) rejected 100% of them.
2. **Low speaker similarity flood**: 161/164 placed segments had
   ``speaker_similarity`` < 0.5; average was 0.321.
3. **Overflow unfitted / compression cap**: 36 segments hit
   ``overflow_unfitted`` because ``max_compress_ratio`` was 1.45.

This test synthesizes the representative pathological signals and asserts our
Sprint 1 + Sprint 2 mitigations prevent a regression:

- resegmented spk_0002 long segments produce *usable* children,
- glossary translates Dubai / Burj Khalifa / UAE without m2m100 hallucinations,
- quality_gate exposes the golden metrics and flags review,
- voice_bank flags thin-pool speakers and borrows from a donor.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import soundfile as sf

from translip.dubbing.planning import try_resegment_for_task_d
from translip.dubbing.voice_bank import (
    VoiceBankRequest,
    apply_cross_speaker_fallback,
    build_voice_bank,
)
from translip.rendering.export import _build_content_quality
from translip.translation.glossary import (
    apply_glossary,
    built_in_dubbing_glossary,
)


# Fixture #1: spk_0002 segments recovered from "silent drop" ------------------


SPK_0002_SEGMENTS = [
    # (segment_id, start, end, text)
    (
        "spk_0002_seg_001",
        100.0,
        108.9,
        "我们终于到了迪拜这座神奇的城市，大家快看哈利法塔。",
    ),
    (
        "spk_0002_seg_002",
        110.0,
        130.0,
        "哈利法塔高达八百二十八米，是阿联酋甚至全世界第一高楼，今天我们要上到观景台。",
    ),
    (
        "spk_0002_seg_003",
        200.0,
        234.9,
        "接下来我们去棕榈岛，看音乐喷泉和帆船酒店，晚上还要在迪拜购物中心逛一圈。",
    ),
]


def test_spk_0002_no_longer_silently_dropped() -> None:
    """Each long spk_0002 segment must yield at least one usable child."""

    for seg_id, start, end, text in SPK_0002_SEGMENTS:
        children = try_resegment_for_task_d(
            segment_id=seg_id,
            start=start,
            end=end,
            text=text,
        )
        assert children, (
            f"Regression! resegment lost {seg_id} (duration={end - start:.1f}s)"
        )
        for child in children:
            # Sprint 2 hard guarantee: every child is within task-d usable bounds.
            assert 1.0 <= child.duration <= 6.0, (
                f"{seg_id} child {child.segment_id} duration={child.duration} "
                "escaped usable window"
            )


# Fixture #2: m2m100-style mistranslation prevention --------------------------


def test_glossary_fixes_dubai_and_burj_khalifa_translations() -> None:
    glossary = built_in_dubbing_glossary(source_lang="zh", target_lang="en")
    # Words the buggy m2m100 model was producing: "Halifa Tower", "Alibaba".
    source_sentences = [
        ("我在迪拜的哈利法塔下面等你", ["Dubai", "Burj Khalifa"]),
        ("阿联酋最有名的是哈里法塔", ["the United Arab Emirates", "Burj Khalifa"]),
        ("我们去阿布扎比看棕榈岛", ["Abu Dhabi", "Palm Jumeirah"]),
    ]
    for source, expected_terms in source_sentences:
        processed, matches = apply_glossary(
            source,
            target_lang="en",
            glossary=glossary,
        )
        for term in expected_terms:
            assert term in processed, (
                f"Glossary failed to normalise {source!r} — expected {term!r} "
                f"in {processed!r}"
            )
        assert matches, "expected at least one glossary match"


# Fixture #3: quality_gate surfaces the three pathological signals ------------


def test_quality_gate_flags_lowband_similarity_like_task_20260425() -> None:
    """Synthesize similar 161/164 low similarity scenario and assert review."""

    low_sim_placed = [
        {
            "speaker_similarity": 0.32,
            "qa_flags": ["overflow_unfitted"] if i < 36 else [],
        }
        for i in range(161)
    ]
    high_sim_placed = [
        {"speaker_similarity": 0.72, "qa_flags": []}
        for _ in range(3)
    ]
    placed = low_sim_placed + high_sim_placed
    skipped = [{"segment_id": f"skip_{i}"} for i in range(22)]

    quality_summary = {
        "total_count": len(placed) + len(skipped),
        "overall_status_counts": {"failed": 160, "passed": 26},
        "speaker_status_counts": {"failed": 161},
        "intelligibility_status_counts": {"failed": 0},
    }
    report = _build_content_quality(
        placed_count=len(placed),
        skipped_count=len(skipped),
        quality_summary=quality_summary,
        audible_coverage={"failed_count": 0},
        placed_items=placed,
        skipped_items=skipped,
    )

    assert report["status"] in ("review_required", "blocked")
    assert "speaker_similarity_lowband_exceeded" in report["reasons"]
    assert "avg_speaker_similarity_below_floor" in report["reasons"]
    assert report["overflow_unfitted_count"] == 36
    assert report["speaker_similarity_lowband_ratio"] > 0.95
    assert report["avg_speaker_similarity"] is not None
    assert report["avg_speaker_similarity"] < 0.35
    assert "thresholds" in report


# Fixture #4: voice_bank cross-speaker fallback for thin speaker --------------


def _write_audio(path: Path, duration_sec: float, amplitude: float = 0.05) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    waveform = np.ones(int(duration_sec * 16_000), dtype=np.float32) * amplitude
    sf.write(path, waveform, 16_000)


def test_voice_bank_fallback_for_thin_pool_like_spk_0002(tmp_path: Path) -> None:
    """spk_0002 with < 3 usable clips must get a donor fallback attached."""

    # Rich donor speaker with 4 good clips
    donor_clips = [tmp_path / f"donor_{i}.wav" for i in range(4)]
    for clip in donor_clips:
        _write_audio(clip, 9.0)
    # Thin speaker with 1 clip only (represents spk_0002 after initial pruning)
    thin_clip = tmp_path / "thin.wav"
    _write_audio(thin_clip, 9.0)

    profiles_path = tmp_path / "profiles.json"
    profiles_path.write_text(
        json.dumps(
            {
                "profiles": [
                    {
                        "profile_id": "profile_donor",
                        "speaker_id": "spk_0001",
                        "source_label": "SPEAKER_01",
                        "segment_count": 40,
                        "total_speech_sec": 80.0,
                        "reference_clips": [
                            {
                                "path": str(clip),
                                "duration": 9.0,
                                "text": "一个长而稳定的参考音频片段",
                                "rms": 0.05,
                            }
                            for clip in donor_clips
                        ],
                    },
                    {
                        "profile_id": "profile_thin",
                        "speaker_id": "spk_0002",
                        "source_label": "SPEAKER_02",
                        "segment_count": 6,
                        "total_speech_sec": 9.0,
                        "reference_clips": [
                            {
                                "path": str(thin_clip),
                                "duration": 9.0,
                                "text": "一个孤立的参考片段",
                                "rms": 0.05,
                            }
                        ],
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = build_voice_bank(
        VoiceBankRequest(
            profiles_path=profiles_path,
            output_dir=tmp_path / "voice-bank",
            include_composites=False,
        )
    )
    speakers = {s.get("speaker_id"): s for s in result.voice_bank["speakers"]}
    assert speakers["spk_0001"]["bank_status"] == "available"
    thin = speakers["spk_0002"]
    assert thin["bank_status"] == "needs_more_references"
    fallback = thin["cross_speaker_fallback"]
    assert fallback is not None
    assert fallback["donor_speaker_id"] == "spk_0001"


def test_apply_cross_speaker_fallback_is_idempotent() -> None:
    """Calling cross-speaker fallback twice must not grow the payload."""

    voice_bank = {
        "speakers": [
            {
                "speaker_id": "spk_a",
                "profile_id": "profile_a",
                "bank_status": "needs_more_references",
                "usable_source_reference_count": 1,
                "references": [],
                "cross_speaker_fallback": None,
            },
            {
                "speaker_id": "spk_b",
                "profile_id": "profile_b",
                "bank_status": "available",
                "usable_source_reference_count": 4,
                "recommended_reference_id": "b-ref",
                "recommended_reference_path": "/tmp/b-ref.wav",
                "total_speech_sec": 20.0,
                "references": [{"reference_id": "b-ref", "quality_score": 0.8}],
                "cross_speaker_fallback": None,
            },
        ]
    }
    apply_cross_speaker_fallback(voice_bank)
    first = json.dumps(voice_bank, sort_keys=True)
    apply_cross_speaker_fallback(voice_bank)
    second = json.dumps(voice_bank, sort_keys=True)
    assert first == second
