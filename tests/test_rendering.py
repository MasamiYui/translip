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
                    "generated_duration_sec": 1.30,
                    "speaker_similarity": 0.68,
                    "speaker_status": "passed",
                    "text_similarity": 0.97,
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
                    "speaker_status": "review",
                    "text_similarity": 0.90,
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
                    "speaker_status": "review",
                    "text_similarity": 0.88,
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

    item_by_id = {item["segment_id"]: item for item in timeline["items"]}
    assert item_by_id["seg-0001"]["mix_status"] == "placed"
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
