import json
from pathlib import Path

import numpy as np
import soundfile as sf

from translip.rendering.runner import render_dub
from translip.types import RenderDubRequest


def _write_tone(path: Path, *, duration_sec: float, sample_rate: int = 24_000, frequency: float = 220.0) -> None:
    sample_count = max(1, int(round(duration_sec * sample_rate)))
    time_axis = np.linspace(0.0, duration_sec, sample_count, endpoint=False, dtype=np.float32)
    waveform = (0.1 * np.sin(2 * np.pi * frequency * time_axis)).astype(np.float32)
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, waveform, sample_rate)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_render_dub_writes_outputs_and_places_failed_segments_when_audio_exists(tmp_path: Path) -> None:
    background_path = tmp_path / "background.wav"
    _write_tone(background_path, duration_sec=4.0, frequency=110.0)

    segments_path = tmp_path / "task-a" / "voice" / "segments.zh.json"
    _write_json(
        segments_path,
        {
            "segments": [
                {
                    "id": "seg-0001",
                    "start": 0.0,
                    "end": 1.0,
                    "duration": 1.0,
                    "speaker_label": "SPEAKER_00",
                    "text": "第一句",
                    "language": "zh",
                },
                {
                    "id": "seg-0002",
                    "start": 1.0,
                    "end": 2.0,
                    "duration": 1.0,
                    "speaker_label": "SPEAKER_00",
                    "text": "第二句",
                    "language": "zh",
                },
                {
                    "id": "seg-0003",
                    "start": 1.2,
                    "end": 2.2,
                    "duration": 1.0,
                    "speaker_label": "SPEAKER_01",
                    "text": "第三句",
                    "language": "zh",
                },
                {
                    "id": "seg-0004",
                    "start": 2.4,
                    "end": 3.4,
                    "duration": 1.0,
                    "speaker_label": "SPEAKER_01",
                    "text": "第四句",
                    "language": "zh",
                },
            ]
        },
    )

    translation_path = tmp_path / "task-c" / "voice" / "translation.en.json"
    _write_json(
        translation_path,
        {
            "backend": {
                "target_lang": "en",
                "output_tag": "en",
            },
            "segments": [
                {
                    "segment_id": "seg-0001",
                    "speaker_id": "spk_0000",
                    "speaker_label": "SPEAKER_00",
                    "start": 0.0,
                    "end": 1.0,
                    "duration": 1.0,
                    "target_text": "first line",
                    "qa_flags": [],
                },
                {
                    "segment_id": "seg-0002",
                    "speaker_id": "spk_0000",
                    "speaker_label": "SPEAKER_00",
                    "start": 1.0,
                    "end": 2.0,
                    "duration": 1.0,
                    "target_text": "second line",
                    "qa_flags": [],
                },
                {
                    "segment_id": "seg-0003",
                    "speaker_id": "spk_0001",
                    "speaker_label": "SPEAKER_01",
                    "start": 1.2,
                    "end": 2.2,
                    "duration": 1.0,
                    "target_text": "third line",
                    "qa_flags": [],
                },
                {
                    "segment_id": "seg-0004",
                    "speaker_id": "spk_0001",
                    "speaker_label": "SPEAKER_01",
                    "start": 2.4,
                    "end": 3.4,
                    "duration": 1.0,
                    "target_text": "fourth line",
                    "qa_flags": [],
                },
            ],
        },
    )

    seg1_audio = tmp_path / "task-d" / "spk_0000" / "segments" / "seg-0001.wav"
    seg2_audio = tmp_path / "task-d" / "spk_0000" / "segments" / "seg-0002.wav"
    seg3_audio = tmp_path / "task-d" / "spk_0001" / "segments" / "seg-0003.wav"
    seg4_audio = tmp_path / "task-d" / "spk_0001" / "segments" / "seg-0004.wav"
    _write_tone(seg1_audio, duration_sec=0.95, frequency=220.0)
    _write_tone(seg2_audio, duration_sec=1.30, frequency=240.0)
    _write_tone(seg3_audio, duration_sec=1.05, frequency=260.0)
    _write_tone(seg4_audio, duration_sec=2.50, frequency=280.0)

    report_a_path = tmp_path / "task-d" / "voice" / "spk_0000" / "speaker_segments.en.json"
    _write_json(
        report_a_path,
        {
            "backend": {"target_lang": "en"},
            "segments": [
                {
                    "segment_id": "seg-0001",
                    "speaker_id": "spk_0000",
                    "target_text": "first line",
                    "source_duration_sec": 1.0,
                    "generated_duration_sec": 0.95,
                    "speaker_similarity": 0.72,
                    "duration_status": "passed",
                    "speaker_status": "passed",
                    "text_similarity": 0.98,
                    "intelligibility_status": "passed",
                    "overall_status": "passed",
                    "audio_path": str(seg1_audio),
                },
                {
                    "segment_id": "seg-0002",
                    "speaker_id": "spk_0000",
                    "target_text": "second line",
                    "source_duration_sec": 1.0,
                    "generated_duration_sec": 1.30,
                    "speaker_similarity": 0.68,
                    "duration_status": "review",
                    "speaker_status": "passed",
                    "text_similarity": 0.97,
                    "intelligibility_status": "passed",
                    "overall_status": "review",
                    "audio_path": str(seg2_audio),
                },
            ],
        },
    )
    report_b_path = tmp_path / "task-d" / "voice" / "spk_0001" / "speaker_segments.en.json"
    _write_json(
        report_b_path,
        {
            "backend": {"target_lang": "en"},
            "segments": [
                {
                    "segment_id": "seg-0003",
                    "speaker_id": "spk_0001",
                    "target_text": "third line",
                    "source_duration_sec": 1.0,
                    "generated_duration_sec": 1.05,
                    "speaker_similarity": 0.35,
                    "duration_status": "review",
                    "speaker_status": "review",
                    "text_similarity": 0.90,
                    "intelligibility_status": "passed",
                    "overall_status": "review",
                    "audio_path": str(seg3_audio),
                },
                {
                    "segment_id": "seg-0004",
                    "speaker_id": "spk_0001",
                    "target_text": "fourth line",
                    "source_duration_sec": 1.0,
                    "generated_duration_sec": 2.50,
                    "speaker_similarity": 0.40,
                    "duration_status": "failed",
                    "speaker_status": "review",
                    "text_similarity": 0.88,
                    "intelligibility_status": "failed",
                    "overall_status": "failed",
                    "audio_path": str(seg4_audio),
                },
            ],
        },
    )

    result = render_dub(
        RenderDubRequest(
            background_path=background_path,
            segments_path=segments_path,
            translation_path=translation_path,
            task_d_report_paths=[report_a_path, report_b_path],
            output_dir=tmp_path / "output-task-e",
            target_lang="en",
            fit_policy="conservative",
            fit_backend="atempo",
            mix_profile="preview",
            ducking_mode="static",
            output_sample_rate=24_000,
            preview_format="wav",
        )
    )

    assert result.artifacts.dub_voice_path.exists()
    assert result.artifacts.preview_mix_wav_path.exists()
    assert result.artifacts.timeline_path.exists()
    assert result.artifacts.mix_report_path.exists()
    assert result.artifacts.manifest_path.exists()

    timeline = json.loads(result.artifacts.timeline_path.read_text(encoding="utf-8"))
    mix_report = json.loads(result.artifacts.mix_report_path.read_text(encoding="utf-8"))

    assert mix_report["stats"]["placed_count"] == 3
    assert mix_report["stats"]["skipped_count"] == 1
    assert mix_report["stats"]["fit_strategy_counts"]["direct"] == 1
    assert mix_report["stats"]["fit_strategy_counts"]["compress"] == 1
    assert mix_report["stats"]["fit_strategy_counts"]["overflow_unfitted"] == 1
    assert mix_report["stats"]["skip_reason_counts"]["skipped_overlap"] == 1
    assert "skipped_failed_task_d" not in mix_report["stats"]["skip_reason_counts"]
    assert "skipped_fit" not in mix_report["stats"]["skip_reason_counts"]
    assert mix_report["stats"]["quality_summary"]["total_count"] == 4
    assert mix_report["stats"]["quality_summary"]["overall_status_counts"] == {
        "failed": 1,
        "passed": 1,
        "review": 2,
    }
    assert mix_report["stats"]["quality_summary"]["duration_status_counts"] == {
        "failed": 1,
        "passed": 1,
        "review": 2,
    }
    assert mix_report["stats"]["quality_summary"]["speaker_status_counts"] == {
        "passed": 2,
        "review": 2,
    }
    assert mix_report["stats"]["quality_summary"]["intelligibility_status_counts"] == {
        "failed": 1,
        "passed": 3,
    }
    assert mix_report["stats"]["quality_summary"]["failure_reason_counts"] == {
        "duration+intelligibility": 1,
    }
    assert mix_report["stats"]["content_quality"]["status"] == "blocked"
    assert "upstream_failed_segments" in mix_report["stats"]["content_quality"]["reasons"]

    item_by_id = {item["segment_id"]: item for item in timeline["items"]}
    assert item_by_id["seg-0001"]["mix_status"] == "placed"
    assert item_by_id["seg-0001"]["duration_status"] == "passed"
    assert item_by_id["seg-0001"]["speaker_status"] == "passed"
    assert item_by_id["seg-0001"]["intelligibility_status"] == "passed"
    assert item_by_id["seg-0002"]["fit_strategy"] == "compress"
    assert item_by_id["seg-0002"]["mix_status"] == "placed"
    assert item_by_id["seg-0003"]["mix_status"] == "skipped_overlap"
    assert item_by_id["seg-0004"]["mix_status"] == "placed"
    assert item_by_id["seg-0004"]["overall_status"] == "failed"
    assert item_by_id["seg-0004"]["fit_strategy"] == "overflow_unfitted"

    dub_waveform, dub_sample_rate = sf.read(result.artifacts.dub_voice_path, dtype="float32")
    preview_waveform, preview_sample_rate = sf.read(result.artifacts.preview_mix_wav_path, dtype="float32")
    assert dub_sample_rate == 24_000
    assert preview_sample_rate == 24_000
    assert len(dub_waveform) == len(preview_waveform)
    assert len(dub_waveform) == int(round(4.0 * 24_000))


def test_render_dub_uses_selected_segments_override(tmp_path: Path) -> None:
    background_path = tmp_path / "background.wav"
    _write_tone(background_path, duration_sec=2.0, frequency=110.0)

    segments_path = tmp_path / "task-a" / "voice" / "segments.zh.json"
    _write_json(
        segments_path,
        {
            "segments": [
                {
                    "id": "seg-0001",
                    "start": 0.0,
                    "end": 1.0,
                    "duration": 1.0,
                    "speaker_label": "SPEAKER_00",
                    "text": "第一句",
                    "language": "zh",
                }
            ]
        },
    )
    translation_path = tmp_path / "task-c" / "voice" / "translation.en.json"
    _write_json(
        translation_path,
        {
            "backend": {"target_lang": "en", "output_tag": "en"},
            "segments": [
                {
                    "segment_id": "seg-0001",
                    "speaker_id": "spk_0000",
                    "speaker_label": "SPEAKER_00",
                    "start": 0.0,
                    "end": 1.0,
                    "duration": 1.0,
                    "target_text": "bad line",
                    "qa_flags": [],
                }
            ],
        },
    )
    original_audio = tmp_path / "task-d" / "voice" / "spk_0000" / "segments" / "seg-0001.wav"
    repaired_audio = tmp_path / "repair" / "seg-0001.wav"
    _write_tone(original_audio, duration_sec=2.4, frequency=220.0)
    _write_tone(repaired_audio, duration_sec=0.9, frequency=330.0)
    report_path = tmp_path / "task-d" / "voice" / "spk_0000" / "speaker_segments.en.json"
    _write_json(
        report_path,
        {
            "backend": {"target_lang": "en"},
            "segments": [
                {
                    "segment_id": "seg-0001",
                    "speaker_id": "spk_0000",
                    "target_text": "bad line",
                    "source_duration_sec": 1.0,
                    "generated_duration_sec": 2.4,
                    "speaker_similarity": 0.2,
                    "speaker_status": "failed",
                    "text_similarity": 0.4,
                    "overall_status": "failed",
                    "audio_path": str(original_audio),
                }
            ],
        },
    )
    selected_path = tmp_path / "repair" / "selected_segments.en.json"
    _write_json(
        selected_path,
        {
            "target_lang": "en",
            "segments": [
                {
                    "segment_id": "seg-0001",
                    "speaker_id": "spk_0000",
                    "target_text": "good line",
                    "selected_audio_path": str(repaired_audio),
                    "selected_attempt_id": "attempt-0001",
                    "generated_duration_sec": 0.9,
                    "duration_ratio": 0.9,
                    "duration_status": "passed",
                    "speaker_similarity": 0.7,
                    "speaker_status": "passed",
                    "text_similarity": 0.98,
                    "intelligibility_status": "passed",
                    "overall_status": "passed",
                }
            ],
        },
    )

    result = render_dub(
        RenderDubRequest(
            background_path=background_path,
            segments_path=segments_path,
            translation_path=translation_path,
            task_d_report_paths=[report_path],
            output_dir=tmp_path / "output-task-e",
            selected_segments_path=selected_path,
            quality_gate="strict",
            target_lang="en",
            fit_policy="conservative",
            fit_backend="atempo",
            mix_profile="preview",
            ducking_mode="static",
            output_sample_rate=24_000,
            preview_format="wav",
        )
    )

    timeline = json.loads(result.artifacts.timeline_path.read_text(encoding="utf-8"))
    item = timeline["items"][0]
    assert item["audio_path"] == str(repaired_audio.resolve())
    assert item["target_text"] == "good line"
    assert item["overall_status"] == "passed"
    assert item["fit_strategy"] == "direct"
    assert item["notes"] == ["selected_repair_attempt:attempt-0001"]


def test_render_dub_exports_optional_mp3_preview(tmp_path: Path) -> None:
    background_path = tmp_path / "background.wav"
    _write_tone(background_path, duration_sec=2.0, frequency=100.0)

    segments_path = tmp_path / "task-a" / "voice" / "segments.zh.json"
    translation_path = tmp_path / "task-c" / "voice" / "translation.en.json"
    segment_audio = tmp_path / "task-d" / "voice" / "spk_0000" / "segments" / "seg-0001.wav"
    report_path = tmp_path / "task-d" / "voice" / "spk_0000" / "speaker_segments.en.json"

    _write_tone(segment_audio, duration_sec=1.0, frequency=200.0)
    _write_json(
        segments_path,
        {
            "segments": [
                {
                    "id": "seg-0001",
                    "start": 0.2,
                    "end": 1.2,
                    "duration": 1.0,
                    "speaker_label": "SPEAKER_00",
                    "text": "一句话",
                    "language": "zh",
                }
            ]
        },
    )
    _write_json(
        translation_path,
        {
            "backend": {"target_lang": "en", "output_tag": "en"},
            "segments": [
                {
                    "segment_id": "seg-0001",
                    "speaker_id": "spk_0000",
                    "speaker_label": "SPEAKER_00",
                    "start": 0.2,
                    "end": 1.2,
                    "duration": 1.0,
                    "target_text": "one line",
                    "qa_flags": [],
                }
            ],
        },
    )
    _write_json(
        report_path,
        {
            "backend": {"target_lang": "en"},
            "segments": [
                {
                    "segment_id": "seg-0001",
                    "speaker_id": "spk_0000",
                    "target_text": "one line",
                    "source_duration_sec": 1.0,
                    "generated_duration_sec": 1.0,
                    "speaker_similarity": 0.70,
                    "speaker_status": "passed",
                    "text_similarity": 0.95,
                    "overall_status": "passed",
                    "audio_path": str(segment_audio),
                }
            ],
        },
    )

    result = render_dub(
        RenderDubRequest(
            background_path=background_path,
            segments_path=segments_path,
            translation_path=translation_path,
            task_d_report_paths=[report_path],
            output_dir=tmp_path / "output-task-e",
            target_lang="en",
            preview_format="mp3",
        )
    )

    assert result.artifacts.preview_mix_wav_path.exists()
    assert result.artifacts.preview_mix_extra_path is not None
    assert result.artifacts.preview_mix_extra_path.exists()


def test_render_dub_uses_ocr_dubbing_window_and_reports_subtitle_coverage(tmp_path: Path) -> None:
    background_path = tmp_path / "background.wav"
    _write_tone(background_path, duration_sec=20.0, frequency=100.0)

    segments_path = tmp_path / "task-a" / "voice" / "segments.zh.corrected.json"
    translation_path = tmp_path / "task-c" / "voice" / "translation.en.json"
    report_path = tmp_path / "task-d" / "voice" / "spk_0000" / "speaker_segments.en.json"
    segment_audio = tmp_path / "task-d" / "voice" / "spk_0000" / "segments" / "seg-0006.wav"
    _write_tone(segment_audio, duration_sec=2.46, frequency=220.0)

    _write_json(
        segments_path,
        {
            "segments": [
                {
                    "id": "seg-0006",
                    "start": 13.35,
                    "end": 18.11,
                    "duration": 4.76,
                    "speaker_label": "SPEAKER_00",
                    "text": "召集全体成员",
                    "timing": {
                        "asr_window": {"start": 13.35, "end": 18.11, "duration": 4.76},
                        "ocr_window": {
                            "start": 16.25,
                            "end": 17.75,
                            "duration": 1.5,
                            "event_ids": ["evt-0006"],
                            "confidence": 0.999,
                        },
                        "subtitle_window": {"start": 16.25, "end": 17.75, "duration": 1.5},
                        "dubbing_window": {
                            "start": 15.65,
                            "end": 18.11,
                            "duration": 2.46,
                            "policy": "late_ocr_anchor",
                        },
                    },
                }
            ]
        },
    )
    _write_json(
        translation_path,
        {
            "backend": {"target_lang": "en", "output_tag": "en"},
            "segments": [
                {
                    "segment_id": "seg-0006",
                    "speaker_id": "spk_0000",
                    "speaker_label": "SPEAKER_00",
                    "start": 13.35,
                    "end": 18.11,
                    "duration": 4.76,
                    "target_text": "Assemble everyone.",
                    "qa_flags": [],
                }
            ],
        },
    )
    _write_json(
        report_path,
        {
            "backend": {"target_lang": "en"},
            "segments": [
                {
                    "segment_id": "seg-0006",
                    "speaker_id": "spk_0000",
                    "target_text": "Assemble everyone.",
                    "source_duration_sec": 4.76,
                    "generated_duration_sec": 2.46,
                    "speaker_similarity": 0.72,
                    "duration_status": "passed",
                    "speaker_status": "passed",
                    "text_similarity": 0.98,
                    "intelligibility_status": "passed",
                    "overall_status": "passed",
                    "audio_path": str(segment_audio),
                }
            ],
        },
    )

    result = render_dub(
        RenderDubRequest(
            background_path=background_path,
            segments_path=segments_path,
            translation_path=translation_path,
            task_d_report_paths=[report_path],
            output_dir=tmp_path / "output-task-e",
            target_lang="en",
            output_sample_rate=24_000,
            preview_format="wav",
        )
    )

    timeline = json.loads(result.artifacts.timeline_path.read_text(encoding="utf-8"))
    mix_report = json.loads(result.artifacts.mix_report_path.read_text(encoding="utf-8"))
    item = timeline["items"][0]

    assert item["anchor_start"] == 15.65
    assert item["anchor_end"] == 18.11
    assert item["source_duration_sec"] == 2.46
    assert item["placement_start"] == 15.65
    assert item["subtitle_window"] == {"start": 16.25, "end": 17.75, "duration": 1.5}
    assert item["subtitle_coverage_ratio"] == 1.0
    assert mix_report["stats"]["audible_coverage"]["subtitle_window_count"] == 1
    assert mix_report["stats"]["audible_coverage"]["failed_count"] == 0


def test_render_dub_blocks_content_quality_when_subtitle_window_has_no_dub_audio(tmp_path: Path) -> None:
    background_path = tmp_path / "background.wav"
    _write_tone(background_path, duration_sec=5.0, frequency=100.0)

    segments_path = tmp_path / "task-a" / "voice" / "segments.zh.corrected.json"
    translation_path = tmp_path / "task-c" / "voice" / "translation.en.json"
    report_path = tmp_path / "task-d" / "voice" / "spk_0000" / "speaker_segments.en.json"
    segment_audio = tmp_path / "task-d" / "voice" / "spk_0000" / "segments" / "seg-0001.wav"
    _write_tone(segment_audio, duration_sec=1.0, frequency=220.0)

    _write_json(
        segments_path,
        {
            "segments": [
                {
                    "id": "seg-0001",
                    "start": 0.0,
                    "end": 1.0,
                    "duration": 1.0,
                    "speaker_label": "SPEAKER_00",
                    "text": "一句话",
                    "timing": {
                        "subtitle_window": {"start": 2.0, "end": 3.0, "duration": 1.0},
                        "dubbing_window": {"start": 0.0, "end": 1.0, "duration": 1.0, "policy": "asr_anchor"},
                    },
                }
            ]
        },
    )
    _write_json(
        translation_path,
        {
            "backend": {"target_lang": "en", "output_tag": "en"},
            "segments": [
                {
                    "segment_id": "seg-0001",
                    "speaker_id": "spk_0000",
                    "speaker_label": "SPEAKER_00",
                    "start": 0.0,
                    "end": 1.0,
                    "duration": 1.0,
                    "target_text": "One line.",
                    "qa_flags": [],
                }
            ],
        },
    )
    _write_json(
        report_path,
        {
            "backend": {"target_lang": "en"},
            "segments": [
                {
                    "segment_id": "seg-0001",
                    "speaker_id": "spk_0000",
                    "target_text": "One line.",
                    "source_duration_sec": 1.0,
                    "generated_duration_sec": 1.0,
                    "speaker_similarity": 0.72,
                    "duration_status": "passed",
                    "speaker_status": "passed",
                    "text_similarity": 0.98,
                    "intelligibility_status": "passed",
                    "overall_status": "passed",
                    "audio_path": str(segment_audio),
                }
            ],
        },
    )

    result = render_dub(
        RenderDubRequest(
            background_path=background_path,
            segments_path=segments_path,
            translation_path=translation_path,
            task_d_report_paths=[report_path],
            output_dir=tmp_path / "output-task-e",
            target_lang="en",
            output_sample_rate=24_000,
            preview_format="wav",
        )
    )

    mix_report = json.loads(result.artifacts.mix_report_path.read_text(encoding="utf-8"))
    item = json.loads(result.artifacts.timeline_path.read_text(encoding="utf-8"))["items"][0]

    assert item["subtitle_coverage_ratio"] == 0.0
    assert "subtitle_window_not_covered" in item["notes"]
    assert mix_report["stats"]["audible_coverage"]["failed_count"] == 1
    assert mix_report["stats"]["content_quality"]["status"] == "blocked"
    assert "audible_coverage_failed" in mix_report["stats"]["content_quality"]["reasons"]


def test_render_dub_shifts_nearby_subtitle_window_start_to_preserve_coverage(tmp_path: Path) -> None:
    background_path = tmp_path / "background.wav"
    _write_tone(background_path, duration_sec=3.0, frequency=100.0)

    segments_path = tmp_path / "task-a" / "voice" / "segments.zh.corrected.json"
    translation_path = tmp_path / "task-c" / "voice" / "translation.en.json"
    report_path = tmp_path / "task-d" / "voice" / "spk_0000" / "speaker_segments.en.json"
    segment_audio = tmp_path / "task-d" / "voice" / "spk_0000" / "segments" / "seg-0001.wav"
    _write_tone(segment_audio, duration_sec=1.0, frequency=220.0)

    _write_json(
        segments_path,
        {
            "segments": [
                {
                    "id": "seg-0001",
                    "start": 0.8,
                    "end": 1.8,
                    "duration": 1.0,
                    "speaker_label": "SPEAKER_00",
                    "text": "一句话",
                    "timing": {
                        "subtitle_window": {"start": 0.0, "end": 1.0, "duration": 1.0},
                        "dubbing_window": {"start": 0.8, "end": 1.8, "duration": 1.0, "policy": "asr_anchor"},
                    },
                }
            ]
        },
    )
    _write_json(
        translation_path,
        {
            "backend": {"target_lang": "en", "output_tag": "en"},
            "segments": [
                {
                    "segment_id": "seg-0001",
                    "speaker_id": "spk_0000",
                    "speaker_label": "SPEAKER_00",
                    "start": 0.8,
                    "end": 1.8,
                    "duration": 1.0,
                    "target_text": "One line.",
                    "qa_flags": [],
                }
            ],
        },
    )
    _write_json(
        report_path,
        {
            "backend": {"target_lang": "en"},
            "segments": [
                {
                    "segment_id": "seg-0001",
                    "speaker_id": "spk_0000",
                    "target_text": "One line.",
                    "source_duration_sec": 1.0,
                    "generated_duration_sec": 1.0,
                    "speaker_similarity": 0.72,
                    "duration_status": "passed",
                    "speaker_status": "passed",
                    "text_similarity": 0.98,
                    "intelligibility_status": "passed",
                    "overall_status": "passed",
                    "audio_path": str(segment_audio),
                }
            ],
        },
    )

    result = render_dub(
        RenderDubRequest(
            background_path=background_path,
            segments_path=segments_path,
            translation_path=translation_path,
            task_d_report_paths=[report_path],
            output_dir=tmp_path / "output-task-e",
            target_lang="en",
            output_sample_rate=24_000,
            preview_format="wav",
        )
    )

    item = json.loads(result.artifacts.timeline_path.read_text(encoding="utf-8"))["items"][0]
    mix_report = json.loads(result.artifacts.mix_report_path.read_text(encoding="utf-8"))

    assert item["placement_start"] == 0.0
    assert item["subtitle_coverage_ratio"] == 1.0
    assert "placement_shifted_to_subtitle_start" in item["notes"]
    assert mix_report["stats"]["audible_coverage"]["failed_count"] == 0


def test_render_dub_layers_subtitle_window_overlap_instead_of_silencing(tmp_path: Path) -> None:
    background_path = tmp_path / "background.wav"
    _write_tone(background_path, duration_sec=3.0, frequency=100.0)

    segments_path = tmp_path / "task-a" / "voice" / "segments.zh.corrected.json"
    translation_path = tmp_path / "task-c" / "voice" / "translation.en.json"
    report_path = tmp_path / "task-d" / "voice" / "spk_0000" / "speaker_segments.en.json"
    seg1_audio = tmp_path / "task-d" / "voice" / "spk_0000" / "segments" / "seg-0001.wav"
    seg2_audio = tmp_path / "task-d" / "voice" / "spk_0000" / "segments" / "seg-0002.wav"
    _write_tone(seg1_audio, duration_sec=2.0, frequency=220.0)
    _write_tone(seg2_audio, duration_sec=1.0, frequency=260.0)

    _write_json(
        segments_path,
        {
            "segments": [
                {
                    "id": "seg-0001",
                    "start": 0.0,
                    "end": 2.0,
                    "duration": 2.0,
                    "speaker_label": "SPEAKER_00",
                    "text": "第一句",
                    "timing": {
                        "subtitle_window": {"start": 0.0, "end": 1.0, "duration": 1.0},
                        "dubbing_window": {"start": 0.0, "end": 2.0, "duration": 2.0, "policy": "asr_anchor"},
                    },
                },
                {
                    "id": "seg-0002",
                    "start": 1.0,
                    "end": 2.0,
                    "duration": 1.0,
                    "speaker_label": "SPEAKER_00",
                    "text": "第二句",
                    "timing": {
                        "subtitle_window": {"start": 1.0, "end": 2.0, "duration": 1.0},
                        "dubbing_window": {"start": 1.0, "end": 2.0, "duration": 1.0, "policy": "asr_anchor"},
                    },
                },
            ]
        },
    )
    _write_json(
        translation_path,
        {
            "backend": {"target_lang": "en", "output_tag": "en"},
            "segments": [
                {
                    "segment_id": "seg-0001",
                    "speaker_id": "spk_0000",
                    "speaker_label": "SPEAKER_00",
                    "start": 0.0,
                    "end": 2.0,
                    "duration": 2.0,
                    "target_text": "First line.",
                    "qa_flags": [],
                },
                {
                    "segment_id": "seg-0002",
                    "speaker_id": "spk_0000",
                    "speaker_label": "SPEAKER_00",
                    "start": 1.0,
                    "end": 2.0,
                    "duration": 1.0,
                    "target_text": "Second line.",
                    "qa_flags": [],
                },
            ],
        },
    )
    _write_json(
        report_path,
        {
            "backend": {"target_lang": "en"},
            "segments": [
                {
                    "segment_id": "seg-0001",
                    "speaker_id": "spk_0000",
                    "target_text": "First line.",
                    "source_duration_sec": 2.0,
                    "generated_duration_sec": 2.0,
                    "speaker_similarity": 0.90,
                    "duration_status": "passed",
                    "speaker_status": "passed",
                    "text_similarity": 0.98,
                    "intelligibility_status": "passed",
                    "overall_status": "passed",
                    "audio_path": str(seg1_audio),
                },
                {
                    "segment_id": "seg-0002",
                    "speaker_id": "spk_0000",
                    "target_text": "Second line.",
                    "source_duration_sec": 1.0,
                    "generated_duration_sec": 1.0,
                    "speaker_similarity": 0.70,
                    "duration_status": "passed",
                    "speaker_status": "passed",
                    "text_similarity": 0.95,
                    "intelligibility_status": "passed",
                    "overall_status": "passed",
                    "audio_path": str(seg2_audio),
                },
            ],
        },
    )

    result = render_dub(
        RenderDubRequest(
            background_path=background_path,
            segments_path=segments_path,
            translation_path=translation_path,
            task_d_report_paths=[report_path],
            output_dir=tmp_path / "output-task-e",
            target_lang="en",
            output_sample_rate=24_000,
            preview_format="wav",
        )
    )

    mix_report = json.loads(result.artifacts.mix_report_path.read_text(encoding="utf-8"))
    item_by_id = {
        item["segment_id"]: item
        for item in json.loads(result.artifacts.timeline_path.read_text(encoding="utf-8"))["items"]
    }

    assert mix_report["stats"]["skipped_count"] == 0
    assert item_by_id["seg-0002"]["mix_status"] == "placed_overlap"
    assert item_by_id["seg-0002"]["subtitle_coverage_ratio"] == 1.0
    assert "overlap_layered_with:seg-0001" in item_by_id["seg-0002"]["notes"]
    assert mix_report["stats"]["audible_coverage"]["failed_count"] == 0
    assert mix_report["stats"]["audible_coverage"]["failed_segment_ids"] == []


def test_render_dub_preserves_subtitle_window_owner_when_later_split_overlaps(tmp_path: Path) -> None:
    background_path = tmp_path / "background.wav"
    _write_tone(background_path, duration_sec=4.0, frequency=100.0)

    segments_path = tmp_path / "task-a" / "voice" / "segments.zh.corrected.json"
    translation_path = tmp_path / "task-c" / "voice" / "translation.en.json"
    report_path = tmp_path / "task-d" / "voice" / "spk_0000" / "speaker_segments.en.json"
    seg1_audio = tmp_path / "task-d" / "voice" / "spk_0000" / "segments" / "seg-0001.wav"
    seg2_audio = tmp_path / "task-d" / "voice" / "spk_0000" / "segments" / "seg-0002.wav"
    _write_tone(seg1_audio, duration_sec=2.0, frequency=220.0)
    _write_tone(seg2_audio, duration_sec=0.8, frequency=260.0)

    _write_json(
        segments_path,
        {
            "segments": [
                {
                    "id": "seg-0001",
                    "start": 0.0,
                    "end": 2.0,
                    "duration": 2.0,
                    "speaker_label": "SPEAKER_00",
                    "text": "第一句",
                    "timing": {
                        "subtitle_window": {"start": 0.0, "end": 2.0, "duration": 2.0},
                        "dubbing_window": {"start": 0.0, "end": 2.0, "duration": 2.0, "policy": "ocr_extended_anchor"},
                    },
                },
                {
                    "id": "seg-0002",
                    "start": 1.0,
                    "end": 1.8,
                    "duration": 0.8,
                    "speaker_label": "SPEAKER_00",
                    "text": "拆分短句",
                },
            ]
        },
    )
    _write_json(
        translation_path,
        {
            "backend": {"target_lang": "en", "output_tag": "en"},
            "segments": [
                {
                    "segment_id": "seg-0001",
                    "speaker_id": "spk_0000",
                    "speaker_label": "SPEAKER_00",
                    "start": 0.0,
                    "end": 2.0,
                    "duration": 2.0,
                    "target_text": "Subtitle owner line.",
                    "qa_flags": [],
                },
                {
                    "segment_id": "seg-0002",
                    "speaker_id": "spk_0000",
                    "speaker_label": "SPEAKER_00",
                    "start": 1.0,
                    "end": 1.8,
                    "duration": 0.8,
                    "target_text": "Split line.",
                    "qa_flags": [],
                },
            ],
        },
    )
    _write_json(
        report_path,
        {
            "backend": {"target_lang": "en"},
            "segments": [
                {
                    "segment_id": "seg-0001",
                    "speaker_id": "spk_0000",
                    "target_text": "Subtitle owner line.",
                    "source_duration_sec": 2.0,
                    "generated_duration_sec": 2.0,
                    "speaker_similarity": 0.31,
                    "duration_status": "passed",
                    "speaker_status": "review",
                    "text_similarity": 0.95,
                    "intelligibility_status": "passed",
                    "overall_status": "failed",
                    "audio_path": str(seg1_audio),
                },
                {
                    "segment_id": "seg-0002",
                    "speaker_id": "spk_0000",
                    "target_text": "Split line.",
                    "source_duration_sec": 0.8,
                    "generated_duration_sec": 0.8,
                    "speaker_similarity": 0.74,
                    "duration_status": "passed",
                    "speaker_status": "passed",
                    "text_similarity": 0.98,
                    "intelligibility_status": "passed",
                    "overall_status": "passed",
                    "audio_path": str(seg2_audio),
                },
            ],
        },
    )

    result = render_dub(
        RenderDubRequest(
            background_path=background_path,
            segments_path=segments_path,
            translation_path=translation_path,
            task_d_report_paths=[report_path],
            output_dir=tmp_path / "output-task-e",
            target_lang="en",
            output_sample_rate=24_000,
            preview_format="wav",
        )
    )

    mix_report = json.loads(result.artifacts.mix_report_path.read_text(encoding="utf-8"))
    item_by_id = {
        item["segment_id"]: item
        for item in json.loads(result.artifacts.timeline_path.read_text(encoding="utf-8"))["items"]
    }

    assert item_by_id["seg-0001"]["mix_status"] == "placed"
    assert item_by_id["seg-0001"]["subtitle_coverage_ratio"] == 1.0
    assert item_by_id["seg-0002"]["mix_status"] == "placed_overlap"
    assert "overlap_layered_with:seg-0001" in item_by_id["seg-0002"]["notes"]
    assert mix_report["stats"]["audible_coverage"]["failed_count"] == 0


def test_render_dub_stretches_short_underflow_when_subtitle_window_would_be_partly_silent(tmp_path: Path) -> None:
    background_path = tmp_path / "background.wav"
    _write_tone(background_path, duration_sec=3.0, frequency=100.0)

    segments_path = tmp_path / "task-a" / "voice" / "segments.zh.corrected.json"
    translation_path = tmp_path / "task-c" / "voice" / "translation.en.json"
    report_path = tmp_path / "task-d" / "voice" / "spk_0000" / "speaker_segments.en.json"
    segment_audio = tmp_path / "task-d" / "voice" / "spk_0000" / "segments" / "seg-0001.wav"
    _write_tone(segment_audio, duration_sec=0.64, frequency=220.0)

    _write_json(
        segments_path,
        {
            "segments": [
                {
                    "id": "seg-0001",
                    "start": 0.0,
                    "end": 1.4,
                    "duration": 1.4,
                    "speaker_label": "SPEAKER_00",
                    "text": "一句话",
                    "timing": {
                        "subtitle_window": {"start": 0.3, "end": 1.4, "duration": 1.1},
                        "dubbing_window": {"start": 0.0, "end": 1.4, "duration": 1.4, "policy": "asr_anchor"},
                    },
                }
            ]
        },
    )
    _write_json(
        translation_path,
        {
            "backend": {"target_lang": "en", "output_tag": "en"},
            "segments": [
                {
                    "segment_id": "seg-0001",
                    "speaker_id": "spk_0000",
                    "speaker_label": "SPEAKER_00",
                    "start": 0.0,
                    "end": 1.4,
                    "duration": 1.4,
                    "target_text": "Go well.",
                    "qa_flags": [],
                }
            ],
        },
    )
    _write_json(
        report_path,
        {
            "backend": {"target_lang": "en"},
            "segments": [
                {
                    "segment_id": "seg-0001",
                    "speaker_id": "spk_0000",
                    "target_text": "Go well.",
                    "source_duration_sec": 1.4,
                    "generated_duration_sec": 0.64,
                    "speaker_similarity": 0.34,
                    "duration_status": "failed",
                    "speaker_status": "review",
                    "text_similarity": 0.90,
                    "intelligibility_status": "review",
                    "overall_status": "failed",
                    "audio_path": str(segment_audio),
                }
            ],
        },
    )

    result = render_dub(
        RenderDubRequest(
            background_path=background_path,
            segments_path=segments_path,
            translation_path=translation_path,
            task_d_report_paths=[report_path],
            output_dir=tmp_path / "output-task-e",
            target_lang="en",
            fit_policy="conservative",
            fit_backend="atempo",
            output_sample_rate=24_000,
            preview_format="wav",
        )
    )

    mix_report = json.loads(result.artifacts.mix_report_path.read_text(encoding="utf-8"))
    item = json.loads(result.artifacts.timeline_path.read_text(encoding="utf-8"))["items"][0]

    assert item["fit_strategy"] == "stretch"
    assert item["fitted_duration_sec"] >= 1.3
    assert item["subtitle_coverage_ratio"] >= 0.9
    assert "underflow_stretched" in item["notes"]
    assert mix_report["stats"]["audible_coverage"]["failed_count"] == 0


def test_render_dub_compresses_small_overruns_to_preserve_adjacent_segments(tmp_path: Path) -> None:
    background_path = tmp_path / "background.wav"
    _write_tone(background_path, duration_sec=3.0, frequency=100.0)

    segments_path = tmp_path / "task-a" / "voice" / "segments.zh.json"
    translation_path = tmp_path / "task-c" / "voice" / "translation.en.json"
    report_path = tmp_path / "task-d" / "voice" / "spk_0000" / "speaker_segments.en.json"
    seg1_audio = tmp_path / "task-d" / "voice" / "spk_0000" / "segments" / "seg-0001.wav"
    seg2_audio = tmp_path / "task-d" / "voice" / "spk_0000" / "segments" / "seg-0002.wav"

    _write_tone(seg1_audio, duration_sec=1.10, frequency=220.0)
    _write_tone(seg2_audio, duration_sec=1.12, frequency=260.0)

    _write_json(
        segments_path,
        {
            "segments": [
                {
                    "id": "seg-0001",
                    "start": 0.0,
                    "end": 1.0,
                    "duration": 1.0,
                    "speaker_label": "SPEAKER_00",
                    "text": "第一句",
                    "language": "zh",
                },
                {
                    "id": "seg-0002",
                    "start": 1.0,
                    "end": 2.0,
                    "duration": 1.0,
                    "speaker_label": "SPEAKER_00",
                    "text": "第二句",
                    "language": "zh",
                },
            ]
        },
    )
    _write_json(
        translation_path,
        {
            "backend": {"target_lang": "en", "output_tag": "en"},
            "segments": [
                {
                    "segment_id": "seg-0001",
                    "speaker_id": "spk_0000",
                    "speaker_label": "SPEAKER_00",
                    "start": 0.0,
                    "end": 1.0,
                    "duration": 1.0,
                    "target_text": "first line",
                    "qa_flags": [],
                },
                {
                    "segment_id": "seg-0002",
                    "speaker_id": "spk_0000",
                    "speaker_label": "SPEAKER_00",
                    "start": 1.0,
                    "end": 2.0,
                    "duration": 1.0,
                    "target_text": "second line",
                    "qa_flags": [],
                },
            ],
        },
    )
    _write_json(
        report_path,
        {
            "backend": {"target_lang": "en"},
            "segments": [
                {
                    "segment_id": "seg-0001",
                    "speaker_id": "spk_0000",
                    "target_text": "first line",
                    "source_duration_sec": 1.0,
                    "generated_duration_sec": 1.10,
                    "speaker_similarity": 0.72,
                    "speaker_status": "passed",
                    "text_similarity": 0.98,
                    "overall_status": "passed",
                    "audio_path": str(seg1_audio),
                },
                {
                    "segment_id": "seg-0002",
                    "speaker_id": "spk_0000",
                    "target_text": "second line",
                    "source_duration_sec": 1.0,
                    "generated_duration_sec": 1.12,
                    "speaker_similarity": 0.71,
                    "speaker_status": "passed",
                    "text_similarity": 0.97,
                    "overall_status": "passed",
                    "audio_path": str(seg2_audio),
                },
            ],
        },
    )

    result = render_dub(
        RenderDubRequest(
            background_path=background_path,
            segments_path=segments_path,
            translation_path=translation_path,
            task_d_report_paths=[report_path],
            output_dir=tmp_path / "output-task-e",
            target_lang="en",
            fit_policy="conservative",
            fit_backend="atempo",
            mix_profile="preview",
            ducking_mode="static",
            output_sample_rate=24_000,
            preview_format="wav",
        )
    )

    mix_report = json.loads(result.artifacts.mix_report_path.read_text(encoding="utf-8"))
    item_by_id = {
        item["segment_id"]: item
        for item in json.loads(result.artifacts.timeline_path.read_text(encoding="utf-8"))["items"]
    }

    assert mix_report["stats"]["placed_count"] == 2
    assert mix_report["stats"]["skipped_count"] == 0
    assert item_by_id["seg-0001"]["fit_strategy"] == "compress"
    assert item_by_id["seg-0002"]["fit_strategy"] == "compress"
    assert item_by_id["seg-0001"]["mix_status"] == "placed"
    assert item_by_id["seg-0002"]["mix_status"] == "placed"


def test_render_dub_compresses_short_risky_overrun_instead_of_dropping_next_segment(tmp_path: Path) -> None:
    background_path = tmp_path / "background.wav"
    _write_tone(background_path, duration_sec=4.0, frequency=90.0)

    segments_path = tmp_path / "task-a" / "voice" / "segments.zh.json"
    translation_path = tmp_path / "task-c" / "voice" / "translation.en.json"
    report_path = tmp_path / "task-d" / "voice" / "spk_0000" / "speaker_segments.en.json"
    seg1_audio = tmp_path / "task-d" / "voice" / "spk_0000" / "segments" / "seg-0010.wav"
    seg2_audio = tmp_path / "task-d" / "voice" / "spk_0000" / "segments" / "seg-0011.wav"

    _write_tone(seg1_audio, duration_sec=1.68, frequency=220.0)
    _write_tone(seg2_audio, duration_sec=1.68, frequency=260.0)

    _write_json(
        segments_path,
        {
            "segments": [
                {
                    "id": "seg-0010",
                    "start": 0.0,
                    "end": 1.0,
                    "duration": 1.0,
                    "speaker_label": "SPEAKER_00",
                    "text": "你是妖",
                    "language": "zh",
                },
                {
                    "id": "seg-0011",
                    "start": 1.0,
                    "end": 2.2,
                    "duration": 1.2,
                    "speaker_label": "SPEAKER_01",
                    "text": "我是魔",
                    "language": "zh",
                },
            ]
        },
    )
    _write_json(
        translation_path,
        {
            "backend": {"target_lang": "en", "output_tag": "en"},
            "segments": [
                {
                    "segment_id": "seg-0010",
                    "speaker_id": "spk_0000",
                    "speaker_label": "SPEAKER_00",
                    "start": 0.0,
                    "end": 1.0,
                    "duration": 1.0,
                    "target_text": "You are the Devil.",
                    "qa_flags": ["duration_risky"],
                },
                {
                    "segment_id": "seg-0011",
                    "speaker_id": "spk_0001",
                    "speaker_label": "SPEAKER_01",
                    "start": 1.0,
                    "end": 2.2,
                    "duration": 1.2,
                    "target_text": "I am the Devil.",
                    "qa_flags": ["duration_may_overrun"],
                },
            ],
        },
    )
    _write_json(
        report_path,
        {
            "backend": {"target_lang": "en"},
            "segments": [
                {
                    "segment_id": "seg-0010",
                    "speaker_id": "spk_0000",
                    "target_text": "You are the Devil.",
                    "source_duration_sec": 1.0,
                    "generated_duration_sec": 1.68,
                    "speaker_similarity": 0.43,
                    "speaker_status": "review",
                    "text_similarity": 0.78,
                    "overall_status": "failed",
                    "audio_path": str(seg1_audio),
                },
                {
                    "segment_id": "seg-0011",
                    "speaker_id": "spk_0001",
                    "target_text": "I am the Devil.",
                    "source_duration_sec": 1.2,
                    "generated_duration_sec": 1.68,
                    "speaker_similarity": 0.39,
                    "speaker_status": "review",
                    "text_similarity": 0.27,
                    "overall_status": "failed",
                    "audio_path": str(seg2_audio),
                },
            ],
        },
    )

    result = render_dub(
        RenderDubRequest(
            background_path=background_path,
            segments_path=segments_path,
            translation_path=translation_path,
            task_d_report_paths=[report_path],
            output_dir=tmp_path / "output-task-e",
            target_lang="en",
            fit_policy="conservative",
            fit_backend="atempo",
            mix_profile="preview",
            ducking_mode="static",
            output_sample_rate=24_000,
            preview_format="wav",
        )
    )

    mix_report = json.loads(result.artifacts.mix_report_path.read_text(encoding="utf-8"))
    item_by_id = {
        item["segment_id"]: item
        for item in json.loads(result.artifacts.timeline_path.read_text(encoding="utf-8"))["items"]
    }

    assert mix_report["stats"]["placed_count"] == 2
    assert mix_report["stats"]["skipped_count"] == 0
    assert item_by_id["seg-0010"]["fit_strategy"] == "compress"
    assert item_by_id["seg-0011"]["fit_strategy"] == "compress"
    assert item_by_id["seg-0010"]["mix_status"] == "placed"
    assert item_by_id["seg-0011"]["mix_status"] == "placed"
