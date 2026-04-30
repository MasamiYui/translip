import json
from pathlib import Path

import numpy as np
import soundfile as sf

from translip.repair import RepairPlanRequest, RepairRunRequest, plan_dub_repair, run_dub_repair
from translip.repair.rewrite import rewrite_for_dubbing
from translip.translation.glossary import GlossaryEntry


def _write_audio(path: Path, duration_sec: float, *, sample_rate: int = 16_000) -> None:
    waveform = 0.05 * np.sin(np.linspace(0, np.pi * 8, int(duration_sec * sample_rate), dtype=np.float32))
    sf.write(path, waveform, sample_rate)


def _write_tone(path: Path, *, frequency: float, duration_sec: float = 1.4, sample_rate: int = 16_000) -> None:
    sample_count = max(1, int(duration_sec * sample_rate))
    time_axis = np.arange(sample_count, dtype=np.float32) / float(sample_rate)
    waveform = (0.08 * np.sin(2 * np.pi * frequency * time_axis)).astype(np.float32)
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, waveform, sample_rate)


class FakeRepairBackend:
    backend_name = "fake-tts"
    resolved_model = "fake-model"
    resolved_device = "cpu"

    def synthesize(self, *, reference, segment, output_path):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        sample_rate = 16_000
        duration_sec = 1.0 if "Burj Khalifa" in segment.target_text else 2.8
        waveform = 0.04 * np.sin(np.linspace(0, np.pi * 8, int(duration_sec * sample_rate), dtype=np.float32))
        sf.write(output_path, waveform, sample_rate)
        return type(
            "SynthOutput",
            (),
            {
                "segment_id": segment.segment_id,
                "audio_path": output_path,
                "sample_rate": sample_rate,
                "generated_duration_sec": duration_sec,
                "backend_metadata": {},
            },
        )()


class HighPitchRepairBackend:
    backend_name = "fake-high-pitch-tts"
    resolved_model = "fake-model"
    resolved_device = "cpu"

    def synthesize(self, *, reference, segment, output_path):
        _write_tone(output_path, frequency=260.0, duration_sec=1.0)
        return type(
            "SynthOutput",
            (),
            {
                "segment_id": segment.segment_id,
                "audio_path": output_path,
                "sample_rate": 16_000,
                "generated_duration_sec": 1.0,
                "backend_metadata": {},
            },
        )()


def _fake_eval(**kwargs):
    target_text = str(kwargs["target_text"])
    passed = "Burj Khalifa" in target_text
    return type(
        "Eval",
        (),
        {
            "speaker_similarity": 0.55 if passed else 0.2,
            "speaker_status": "passed" if passed else "failed",
            "backread_text": target_text,
            "text_similarity": 0.97 if passed else 0.6,
            "intelligibility_status": "passed" if passed else "failed",
            "duration_ratio": 1.0 if passed else 2.4,
            "duration_status": "passed" if passed else "failed",
            "overall_status": "passed" if passed else "failed",
        },
    )()


def _always_pass_eval(**kwargs):
    target_text = str(kwargs["target_text"])
    return type(
        "Eval",
        (),
        {
            "speaker_similarity": 0.82,
            "speaker_status": "passed",
            "backread_text": target_text,
            "text_similarity": 0.99,
            "intelligibility_status": "passed",
            "duration_ratio": 1.0,
            "duration_status": "passed",
            "overall_status": "passed",
        },
    )()


def test_rewrite_for_dubbing_protects_glossary_and_shortens() -> None:
    glossary = [
        GlossaryEntry(
            entry_id="burj-khalifa",
            source_variants=("哈利法塔", "哈里法塔"),
            targets={"en": "Burj Khalifa"},
        )
    ]

    candidates = rewrite_for_dubbing(
        segment_id="seg-0002",
        source_text="奶奶您知道哈利法塔吗",
        current_target_text="Do you know the Halifa Tower?",
        source_duration_sec=2.2,
        target_lang="en",
        glossary=glossary,
    )

    by_variant = {candidate.variant: candidate for candidate in candidates}
    assert by_variant["natural"].target_text == "Do you know the Burj Khalifa?"
    assert by_variant["short"].target_text == "Know Burj Khalifa?"
    assert by_variant["short"].estimated_tts_duration_sec < by_variant["natural"].estimated_tts_duration_sec


def test_rewrite_for_dubbing_fixes_common_bad_phrase() -> None:
    candidates = rewrite_for_dubbing(
        segment_id="seg-0019",
        source_text="打扰一下你是中国人吗",
        current_target_text="Do you bother you are Chinese?",
        source_duration_sec=0.84,
        target_lang="en",
        glossary=[],
    )

    by_variant = {candidate.variant: candidate for candidate in candidates}
    assert by_variant["natural"].target_text == "Excuse me, are you Chinese?"
    assert by_variant["short"].target_text == "Are you Chinese?"


def test_rewrite_for_dubbing_compresses_short_dialogue_phrase() -> None:
    candidates = rewrite_for_dubbing(
        segment_id="seg-0022",
        source_text="我眼力也太好了",
        current_target_text="My eyes are good too.",
        source_duration_sec=1.16,
        target_lang="en",
        glossary=[],
    )

    by_variant = {candidate.variant: candidate for candidate in candidates}
    assert by_variant["natural"].target_text == "Great eyes."
    assert by_variant["natural"].estimated_tts_duration_sec < 1.0


def test_rewrite_for_dubbing_preserves_mid_sentence_contraction_case() -> None:
    candidates = rewrite_for_dubbing(
        segment_id="seg-0023",
        source_text="你成通缉犯了什么逻辑",
        current_target_text="What is the logic you are searching for?",
        source_duration_sec=1.56,
        target_lang="en",
        glossary=[],
    )

    by_variant = {candidate.variant: candidate for candidate in candidates}
    assert by_variant["short"].target_text == "What is the logic you're searching for?"


def test_plan_dub_repair_writes_queue_rewrite_and_reference_plan(tmp_path: Path) -> None:
    translation_path = tmp_path / "translation.en.json"
    profiles_path = tmp_path / "speaker_profiles.json"
    report_path = tmp_path / "speaker_segments.en.json"
    glossary_path = tmp_path / "glossary.json"
    ref_current = tmp_path / "clip_current.wav"
    ref_alt = tmp_path / "clip_alt.wav"
    _write_audio(ref_current, 8.0)
    _write_audio(ref_alt, 8.0)

    translation_path.write_text(
        json.dumps(
            {
                "backend": {"target_lang": "en", "output_tag": "en"},
                "segments": [
                    {
                        "segment_id": "seg-0001",
                        "speaker_id": "spk_0000",
                        "source_text": "奶奶您知道哈利法塔吗",
                        "target_text": "Do you know the Halifa Tower?",
                        "start": 1.0,
                        "end": 3.2,
                        "duration": 2.2,
                        "qa_flags": [],
                    },
                    {
                        "segment_id": "seg-0002",
                        "speaker_id": "spk_0000",
                        "source_text": "迪拜",
                        "target_text": "in Didi",
                        "start": 3.2,
                        "end": 4.0,
                        "duration": 0.8,
                        "qa_flags": ["too_short_source"],
                    },
                    {
                        "segment_id": "seg-0003",
                        "speaker_id": "spk_0000",
                        "source_text": "谢谢",
                        "target_text": "Thank you.",
                        "start": 4.0,
                        "end": 4.9,
                        "duration": 0.9,
                        "qa_flags": ["too_short_source"],
                    },
                ],
            },
            ensure_ascii=False,
        ),
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
                                "path": str(ref_current),
                                "text": "这是当前参考音频，有足够长的文本",
                                "duration": 9.0,
                                "rms": 0.05,
                            },
                            {
                                "path": str(ref_alt),
                                "text": "这是另一个参考音频，也比较稳定",
                                "duration": 8.5,
                                "rms": 0.05,
                            },
                        ],
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    report_path.write_text(
        json.dumps(
            {
                "speaker_id": "spk_0000",
                "reference": {"path": str(ref_current)},
                "segments": [
                    {
                        "segment_id": "seg-0001",
                        "speaker_id": "spk_0000",
                        "target_text": "Do you know the Halifa Tower?",
                        "source_duration_sec": 2.2,
                        "generated_duration_sec": 4.2,
                        "duration_ratio": 1.91,
                        "duration_status": "failed",
                        "speaker_similarity": 0.2,
                        "speaker_status": "failed",
                        "text_similarity": 0.61,
                        "intelligibility_status": "failed",
                        "overall_status": "failed",
                        "audio_path": str(tmp_path / "seg-0001.wav"),
                        "reference_path": str(ref_current),
                    },
                    {
                        "segment_id": "seg-0002",
                        "speaker_id": "spk_0000",
                        "target_text": "in Didi",
                        "source_duration_sec": 0.8,
                        "generated_duration_sec": 2.4,
                        "duration_ratio": 3.0,
                        "duration_status": "failed",
                        "speaker_similarity": 0.5,
                        "speaker_status": "passed",
                        "text_similarity": 1.0,
                        "intelligibility_status": "passed",
                        "overall_status": "failed",
                        "audio_path": str(tmp_path / "seg-0002.wav"),
                        "reference_path": str(ref_current),
                    },
                    {
                        "segment_id": "seg-0003",
                        "speaker_id": "spk_0000",
                        "target_text": "Thank you.",
                        "source_duration_sec": 0.9,
                        "generated_duration_sec": 1.0,
                        "duration_ratio": 1.11,
                        "duration_status": "passed",
                        "speaker_similarity": 0.8,
                        "speaker_status": "passed",
                        "text_similarity": 1.0,
                        "intelligibility_status": "passed",
                        "overall_status": "review",
                        "audio_path": str(tmp_path / "seg-0003.wav"),
                        "reference_path": str(ref_current),
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    glossary_path.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "entry_id": "burj-khalifa",
                        "source_variants": ["哈利法塔"],
                        "targets": {"en": "Burj Khalifa"},
                    },
                    {
                        "entry_id": "dubai",
                        "source_variants": ["迪拜"],
                        "targets": {"en": "Dubai"},
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = plan_dub_repair(
        RepairPlanRequest(
            translation_path=translation_path,
            profiles_path=profiles_path,
            task_d_report_paths=[report_path],
            output_dir=tmp_path / "repair",
            target_lang="en",
            glossary_path=glossary_path,
        )
    )

    repair_queue = json.loads(result.artifacts.repair_queue_path.read_text(encoding="utf-8"))
    rewrite_plan = json.loads(result.artifacts.rewrite_plan_path.read_text(encoding="utf-8"))
    reference_plan = json.loads(result.artifacts.reference_plan_path.read_text(encoding="utf-8"))
    assert repair_queue["stats"]["repair_count"] == 3
    assert repair_queue["stats"]["strict_blocker_count"] == 2
    assert repair_queue["stats"]["risk_only_count"] == 1
    assert repair_queue["stats"]["queue_class_counts"] == {"risk_only": 1, "strict_blocker": 2}
    assert repair_queue["stats"]["reason_counts"]["duration_failed"] == 2
    assert "switch_reference_audio" in repair_queue["items"][0]["suggested_actions"]
    assert repair_queue["items"][0]["queue_class"] == "strict_blocker"
    assert repair_queue["items"][-1]["queue_class"] == "risk_only"
    assert rewrite_plan["item_count"] == 2
    assert rewrite_plan["items"][0]["rewrite_candidates"][0]["target_text"] == "Do you know the Burj Khalifa?"
    assert reference_plan["speaker_count"] == 1
    assert reference_plan["speakers"][0]["current_reference_path"] == str(ref_current)
    assert reference_plan["speakers"][0]["recommended_reference_path"] == str(ref_alt.resolve())
    assert result.manifest["stats"]["repair_count"] == 3
    assert result.manifest["stats"]["strict_blocker_count"] == 2


def test_run_dub_repair_generates_attempts_and_selected_segments(tmp_path: Path) -> None:
    translation_path = tmp_path / "translation.en.json"
    profiles_path = tmp_path / "speaker_profiles.json"
    report_path = tmp_path / "speaker_segments.en.json"
    glossary_path = tmp_path / "glossary.json"
    ref_current = tmp_path / "clip_current.wav"
    ref_alt = tmp_path / "clip_alt.wav"
    _write_audio(ref_current, 8.0)
    _write_audio(ref_alt, 8.0)

    translation_path.write_text(
        json.dumps(
            {
                "backend": {"target_lang": "en", "output_tag": "en"},
                "segments": [
                    {
                        "segment_id": "seg-0001",
                        "speaker_id": "spk_0000",
                        "source_text": "奶奶您知道哈利法塔吗",
                        "target_text": "Do you know the Halifa Tower?",
                        "start": 1.0,
                        "end": 3.2,
                        "duration": 2.2,
                        "qa_flags": [],
                    }
                ],
            },
            ensure_ascii=False,
        ),
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
                                "path": str(ref_current),
                                "text": "这是当前参考音频，有足够长的文本",
                                "duration": 8.0,
                                "rms": 0.05,
                            },
                            {
                                "path": str(ref_alt),
                                "text": "这是另一个参考音频，也比较稳定",
                                "duration": 8.0,
                                "rms": 0.05,
                            },
                        ],
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    report_path.write_text(
        json.dumps(
            {
                "speaker_id": "spk_0000",
                "reference": {"path": str(ref_current)},
                "segments": [
                    {
                        "segment_id": "seg-0001",
                        "speaker_id": "spk_0000",
                        "target_text": "Do you know the Halifa Tower?",
                        "source_duration_sec": 2.2,
                        "generated_duration_sec": 4.2,
                        "duration_ratio": 1.91,
                        "duration_status": "failed",
                        "speaker_similarity": 0.2,
                        "speaker_status": "failed",
                        "text_similarity": 0.61,
                        "intelligibility_status": "failed",
                        "overall_status": "failed",
                        "audio_path": str(tmp_path / "seg-0001.wav"),
                        "reference_path": str(ref_current),
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    glossary_path.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "entry_id": "burj-khalifa",
                        "source_variants": ["哈利法塔"],
                        "targets": {"en": "Burj Khalifa"},
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    plan = plan_dub_repair(
        RepairPlanRequest(
            translation_path=translation_path,
            profiles_path=profiles_path,
            task_d_report_paths=[report_path],
            output_dir=tmp_path / "repair-plan",
            target_lang="en",
            glossary_path=glossary_path,
        )
    )
    run = run_dub_repair(
        RepairRunRequest(
            repair_queue_path=plan.artifacts.repair_queue_path,
            rewrite_plan_path=plan.artifacts.rewrite_plan_path,
            reference_plan_path=plan.artifacts.reference_plan_path,
            output_dir=tmp_path / "repair-run",
            tts_backends=["moss-tts-nano-onnx"],
            max_items=1,
            attempts_per_item=2,
        ),
        backend_override=FakeRepairBackend(),
        evaluator=_fake_eval,
    )

    attempts = json.loads(run.artifacts.attempts_path.read_text(encoding="utf-8"))
    selected = json.loads(run.artifacts.selected_segments_path.read_text(encoding="utf-8"))
    manual = json.loads(run.artifacts.manual_review_path.read_text(encoding="utf-8"))
    assert attempts["stats"]["input_count"] == 1
    assert attempts["stats"]["attempt_count"] == 2
    assert attempts["stats"]["selected_count"] == 1
    assert attempts["items"][0]["selected_attempt"]["target_text"] == "Do you know the Burj Khalifa?"
    assert Path(selected["segments"][0]["selected_audio_path"]).exists()
    assert selected["segments"][0]["overall_status"] == "passed"
    assert manual["stats"]["manual_required_count"] == 0


def test_run_dub_repair_blocks_pitch_class_drift_against_character_ledger(tmp_path: Path) -> None:
    reference = tmp_path / "reference_low.wav"
    _write_tone(reference, frequency=110.0, duration_sec=2.0)

    repair_queue_path = tmp_path / "repair_queue.en.json"
    rewrite_plan_path = tmp_path / "rewrite_plan.en.json"
    reference_plan_path = tmp_path / "reference_plan.en.json"
    ledger_path = tmp_path / "character_ledger.en.json"
    repair_queue_path.write_text(
        json.dumps(
            {
                "target_lang": "en",
                "items": [
                    {
                        "segment_id": "seg-0001",
                        "speaker_id": "spk_0001",
                        "source_text": "走吧",
                        "target_text": "Let's go.",
                        "source_duration_sec": 1.0,
                        "strict_blocker": True,
                        "failure_reasons": ["speaker_failed"],
                        "suggested_actions": ["switch_reference_audio"],
                        "reference_path": str(reference),
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    rewrite_plan_path.write_text(
        json.dumps(
            {
                "target_lang": "en",
                "items": [
                    {
                        "segment_id": "seg-0001",
                        "rewrite_candidates": [
                            {
                                "rewrite_id": "rewrite-0001",
                                "variant": "current",
                                "target_text": "Let's go.",
                                "estimated_tts_duration_sec": 1.0,
                            }
                        ],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    reference_plan_path.write_text(
        json.dumps(
            {
                "target_lang": "en",
                "speakers": [
                    {
                        "speaker_id": "spk_0001",
                        "current_reference_path": str(reference),
                        "recommended_reference_path": str(reference),
                        "candidates": [
                            {
                                "path": str(reference),
                                "profile_id": "profile_0001",
                                "speaker_id": "spk_0001",
                                "duration_sec": 2.0,
                                "text": "低音参考",
                                "rms": 0.08,
                                "quality_score": 0.9,
                            }
                        ],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    ledger_path.write_text(
        json.dumps(
            {
                "target_lang": "en",
                "characters": [
                    {
                        "character_id": "char_0001",
                        "display_name": "Male Lead",
                        "speaker_ids": ["spk_0001"],
                        "voice_signature": {
                            "path": str(reference),
                            "pitch_hz": 110.0,
                            "pitch_class": "low",
                        },
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    run = run_dub_repair(
        RepairRunRequest(
            repair_queue_path=repair_queue_path,
            rewrite_plan_path=rewrite_plan_path,
            reference_plan_path=reference_plan_path,
            character_ledger_path=ledger_path,
            output_dir=tmp_path / "repair-run",
            tts_backends=["moss-tts-nano-onnx"],
            max_items=1,
            attempts_per_item=1,
        ),
        backend_override=HighPitchRepairBackend(),
        evaluator=_always_pass_eval,
    )

    attempts = json.loads(run.artifacts.attempts_path.read_text(encoding="utf-8"))
    selected = json.loads(run.artifacts.selected_segments_path.read_text(encoding="utf-8"))
    manual = json.loads(run.artifacts.manual_review_path.read_text(encoding="utf-8"))
    attempt = attempts["items"][0]["attempts"][0]
    assert attempt["metrics"]["voice_consistency_status"] == "failed"
    assert attempt["metrics"]["expected_pitch_class"] == "low"
    assert attempt["metrics"]["generated_pitch_class"] == "high"
    assert attempt["strict_accepted"] is False
    assert attempts["stats"]["selected_count"] == 0
    assert selected["stats"]["selected_count"] == 0
    assert manual["stats"]["manual_required_count"] == 1
