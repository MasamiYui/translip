from __future__ import annotations

import importlib
import numpy as np
import pytest

from translip.transcription.asr import AsrSegment
from translip.transcription.diarization import (
    DiarizedTurn,
    assign_turns_to_segments,
    create_backend,
    refine_with_change_detection,
    resolve_backend_name,
)
from translip.transcription.diarization.legacy_ecapa import (
    _contiguous_turns,
    _maybe_recluster,
    _nearest_labelled,
    _resolve_recluster_mode,
    _stitch_noise,
)
from translip.transcription.diarization.threed_speaker import (
    ThreeDSpeakerBackend,
    _coerce_speaker,
    _ensure_mono_16k_wav,
    _extract_segments,
    _normalize_dict_segments,
    _normalize_triples,
)


def _segment(segment_id: str, start: float, end: float, text: str = "hi") -> AsrSegment:
    return AsrSegment(
        segment_id=segment_id,
        start=start,
        end=end,
        text=text,
        language="zh",
    )


def test_assign_turns_to_segments_prefers_largest_overlap() -> None:
    segments = [
        _segment("seg-0001", 0.0, 2.0),
        _segment("seg-0002", 2.0, 4.0),
    ]
    turns = [
        DiarizedTurn(start=0.0, end=1.9, speaker_id=0),
        DiarizedTurn(start=1.9, end=4.0, speaker_id=1),
    ]
    outcome = assign_turns_to_segments(segments, turns)
    assert outcome.segment_speaker_ids == [0, 1]
    assert outcome.stats["split_segment_count"] == 0
    assert outcome.stats["fallback_segment_count"] == 0


def test_assign_turns_to_segments_splits_long_multi_speaker_segment() -> None:
    segments = [_segment("seg-0001", 0.0, 12.0, text="long dialogue")]
    turns = [
        DiarizedTurn(start=0.0, end=5.0, speaker_id=0),
        DiarizedTurn(start=5.0, end=12.0, speaker_id=1),
    ]
    outcome = assign_turns_to_segments(segments, turns, long_segment_split_sec=10.0)
    assert outcome.stats["split_segment_count"] == 1
    assert len(outcome.segments) >= 2
    assert outcome.segment_speaker_ids[0] == 0
    assert outcome.segment_speaker_ids[-1] == 1
    assert outcome.segments[0].segment_id.startswith("seg-0001-")


def test_assign_turns_to_segments_fallback_when_no_turn_overlaps() -> None:
    segments = [_segment("seg-0001", 0.0, 2.0)]
    turns = [DiarizedTurn(start=5.0, end=6.0, speaker_id=7)]
    outcome = assign_turns_to_segments(segments, turns)
    assert outcome.segment_speaker_ids == [7]
    assert outcome.stats["fallback_segment_count"] == 1


def test_refine_with_change_detection_smooths_short_sandwich() -> None:
    segments = [
        _segment("seg-0001", 0.0, 1.0),
        _segment("seg-0002", 1.0, 2.0),
        _segment("seg-0003", 2.0, 3.0),
    ]
    turns = [
        DiarizedTurn(start=0.0, end=1.0, speaker_id=0),
        DiarizedTurn(start=1.0, end=2.0, speaker_id=1),
        DiarizedTurn(start=2.0, end=3.0, speaker_id=0),
    ]
    outcome = assign_turns_to_segments(segments, turns)
    outcome = refine_with_change_detection(outcome)
    assert outcome.segment_speaker_ids == [0, 0, 0]


def test_refine_leaves_long_middle_segment_untouched() -> None:
    segments = [
        _segment("seg-0001", 0.0, 1.0),
        _segment("seg-0002", 1.0, 5.0),
        _segment("seg-0003", 5.0, 6.0),
    ]
    turns = [
        DiarizedTurn(start=0.0, end=1.0, speaker_id=0),
        DiarizedTurn(start=1.0, end=5.0, speaker_id=1),
        DiarizedTurn(start=5.0, end=6.0, speaker_id=0),
    ]
    outcome = assign_turns_to_segments(segments, turns)
    outcome = refine_with_change_detection(outcome)
    assert outcome.segment_speaker_ids == [0, 1, 0]


def test_contiguous_turns_merges_consecutive_same_speaker() -> None:
    segments = [
        _segment("seg-0001", 0.0, 1.0),
        _segment("seg-0002", 1.0, 2.0),
        _segment("seg-0003", 2.0, 3.0),
    ]
    turns = _contiguous_turns(segments, [3, 3, 7])
    assert len(turns) == 2
    assert turns[0].speaker_id == 3
    assert turns[1].speaker_id == 7
    assert turns[-1].end == 3.0


def test_resolve_backend_name_honours_aliases() -> None:
    assert resolve_backend_name("ECAPA") == "legacy_ecapa"
    assert resolve_backend_name("3d-speaker") == "threed_speaker"
    assert resolve_backend_name(None) == "auto"
    assert resolve_backend_name("unknown") == "auto"


def test_create_backend_legacy_always_available() -> None:
    backend = create_backend("legacy_ecapa")
    assert backend.is_available()
    assert backend.name == "legacy_ecapa"


def test_create_backend_auto_falls_back_when_modelscope_missing(monkeypatch) -> None:
    import translip.transcription.diarization.factory as factory_module
    from translip.transcription.diarization import threed_speaker as ts_module

    def fake_is_available(self: ts_module.ThreeDSpeakerBackend) -> bool:
        self._last_error = "disabled in tests"
        return False

    monkeypatch.setattr(ts_module.ThreeDSpeakerBackend, "is_available", fake_is_available)
    backend = factory_module.create_backend("auto")
    assert backend.name == "legacy_ecapa"


def test_threed_speaker_normalizers() -> None:
    triples = _normalize_triples([[0.1, 0.5, 0], (0.5, 1.0, "spk_1"), "bad"])
    assert triples == [(0.1, 0.5, 0), (0.5, 1.0, 1)]
    dicts = _normalize_dict_segments(
        [
            {"start": 0.0, "end": 1.0, "speaker": "spk_2"},
            {"begin": 1.0, "end": 2.0, "speaker": 3},
            "not-a-dict",
        ]
    )
    assert dicts == [(0.0, 1.0, 2), (1.0, 2.0, 3)]
    assert _extract_segments({"segments": [{"start": 0, "end": 1, "speaker": 0}]}) == [
        (0.0, 1.0, 0)
    ]
    assert _extract_segments({"text": [[0.0, 1.0, 1]]}) == [(0.0, 1.0, 1)]
    assert _extract_segments("bogus") == []
    assert _coerce_speaker("SPEAKER_07") == 7
    assert _coerce_speaker(True) == 1
    assert _coerce_speaker(None) == 0
    # Regression: modelscope returns numpy scalar types; ``_coerce_speaker``
    # must not silently collapse them to zero.  Missing this broke CAM++
    # integration by turning every turn into SPEAKER_00.
    assert _coerce_speaker(np.int64(5)) == 5
    assert _coerce_speaker(np.int32(2)) == 2
    assert _coerce_speaker(np.float64(3.0)) == 3
    assert _normalize_triples([[np.float64(1.0), np.float64(2.0), np.int64(4)]]) == [
        (1.0, 2.0, 4)
    ]


def test_legacy_backend_reproduces_single_speaker_short_audio() -> None:
    segments = [
        _segment("seg-0001", 0.0, 1.0),
        _segment("seg-0002", 1.0, 2.0),
    ]
    # We only validate that _contiguous_turns degenerates to a single turn for
    # uniform clusters; the full backend is exercised via integration tests.
    turns = _contiguous_turns(segments, [0, 0])
    assert len(turns) == 1
    assert turns[0].start == 0.0
    assert turns[0].end == 2.0


def test_projection_handles_no_turns_gracefully() -> None:
    segments = [_segment("seg-0001", 0.0, 1.0)]
    outcome = assign_turns_to_segments(segments, [])
    assert outcome.segment_speaker_ids == [0]
    assert outcome.stats["fallback_segment_count"] == 1


def test_projection_preserves_input_for_short_multi_speaker_segment() -> None:
    segments = [_segment("seg-0001", 0.0, 4.0)]
    turns = [
        DiarizedTurn(start=0.0, end=2.0, speaker_id=0),
        DiarizedTurn(start=2.0, end=4.0, speaker_id=1),
    ]
    # Short segment should not be split.
    outcome = assign_turns_to_segments(segments, turns, long_segment_split_sec=10.0)
    assert outcome.stats["split_segment_count"] == 0
    assert len(outcome.segments) == 1
    # Speaker should match whichever turn overlaps the most.
    assert outcome.segment_speaker_ids[0] in {0, 1}


def test_assign_speaker_labels_empty_segments() -> None:
    from pathlib import Path

    from translip.transcription.speaker import assign_speaker_labels

    labels, meta = assign_speaker_labels(Path("/tmp/does-not-matter.wav"), [], requested_device="cpu")
    assert labels == []
    assert meta["speaker_count"] == 0
    assert meta["diarization_backend"] in {"auto", "legacy_ecapa", "threed_speaker"}


def test_pairwise_similarities_upper_triangle() -> None:
    # Regression guard for the legacy ECAPA helpers that other tests depend on.
    from translip.transcription.speaker import _pairwise_similarities

    matrix = np.eye(3, dtype=np.float32)
    sims = _pairwise_similarities(matrix)
    assert sims.shape == (3,)
    assert np.allclose(sims, 0.0)


def test_ensure_mono_16k_wav_returns_valid_wav(tmp_path) -> None:
    """The ffmpeg-based resampler must yield a 16 kHz mono WAV readable by
    soundfile so CAM++ does not re-enter torchaudio's missing ``sox_effects``.
    """

    import soundfile as sf

    src = tmp_path / "src.wav"
    sample_rate = 22050
    duration_sec = 0.5
    audio = np.zeros(int(sample_rate * duration_sec), dtype=np.float32)
    sf.write(src, audio, sample_rate)

    out = _ensure_mono_16k_wav(src)
    assert out.exists()
    assert out.suffix == ".wav"
    data, sr = sf.read(out)
    assert sr == 16000
    assert data.ndim == 1
    if out != src:
        out.unlink(missing_ok=True)


def test_ensure_mono_16k_wav_handles_missing_ffmpeg(monkeypatch, tmp_path) -> None:
    src = tmp_path / "src.wav"
    src.write_bytes(b"not-a-wav")
    monkeypatch.setattr(
        "translip.transcription.diarization.threed_speaker.shutil.which",
        lambda _cmd: None,
    )
    out = _ensure_mono_16k_wav(src)
    assert out == src  # falls back gracefully without raising


def test_threed_speaker_is_available_reports_missing_modelscope(monkeypatch) -> None:
    monkeypatch.setattr(
        "translip.transcription.diarization.threed_speaker._has_module",
        lambda name: False,
    )
    backend = ThreeDSpeakerBackend()
    assert backend.is_available() is False
    assert backend._last_error and "modelscope" in backend._last_error.lower()


@pytest.mark.skipif(
    importlib.util.find_spec("modelscope") is None,
    reason="modelscope not installed; skipping live CAM++ integration probe",
)
def test_threed_speaker_can_instantiate_pipeline() -> None:
    """Integration guard: when modelscope is available, ``is_available`` must
    successfully load the CAM++ pipeline without raising.

    This does not run diarization (no audio fixture ≥30 s in tests/), but it
    ensures the optional dependency + pipeline id combination stays healthy.
    """

    backend = ThreeDSpeakerBackend()
    assert backend.is_available() is True
    assert backend._pipeline is not None


def test_resolve_speaker_embedder_name_prefers_auto(monkeypatch) -> None:
    from translip.speaker_embedding import (
        ECAPA_EMBEDDER_NAME,
        ERES2NETV2_EMBEDDER_NAME,
        resolve_speaker_embedder_name,
    )

    monkeypatch.delenv("TRANSLIP_SPEAKER_EMBEDDER", raising=False)

    monkeypatch.setattr(
        "translip.speaker_embedding._has_module",
        lambda name: name in {"modelscope", "funasr"},
    )
    assert resolve_speaker_embedder_name() == ERES2NETV2_EMBEDDER_NAME

    monkeypatch.setattr("translip.speaker_embedding._has_module", lambda _name: False)
    assert resolve_speaker_embedder_name() == ECAPA_EMBEDDER_NAME


def test_resolve_speaker_embedder_name_respects_explicit_choice(monkeypatch) -> None:
    from translip.speaker_embedding import (
        ECAPA_EMBEDDER_NAME,
        ERES2NETV2_EMBEDDER_NAME,
        resolve_speaker_embedder_name,
    )

    assert resolve_speaker_embedder_name("speechbrain-ecapa") == ECAPA_EMBEDDER_NAME
    assert resolve_speaker_embedder_name("eres2netv2") == ERES2NETV2_EMBEDDER_NAME
    assert resolve_speaker_embedder_name("eres2net") == ERES2NETV2_EMBEDDER_NAME
    assert resolve_speaker_embedder_name("unknown") == ECAPA_EMBEDDER_NAME


def test_get_speaker_embedder_falls_back_when_eres2net_fails(monkeypatch) -> None:
    from translip import speaker_embedding as se

    se._cached_embedder.cache_clear()

    class _StubEcapa(se.SpeakerEmbedder):
        name = se.ECAPA_EMBEDDER_NAME
        embedding_dim = 192

        def __init__(self, device: str) -> None:
            self._device = device

        def encode(self, clip, sample_rate):
            return np.zeros(192, dtype=np.float32)

    def _boom() -> None:
        raise RuntimeError("modelscope unavailable")

    monkeypatch.setattr(se, "_EcapaEmbedder", _StubEcapa)
    monkeypatch.setattr(se, "_Eres2NetV2Embedder", lambda: _boom())

    embedder = se.get_speaker_embedder("cpu", name="eres2netv2")
    assert isinstance(embedder, _StubEcapa)
    assert embedder.name == se.ECAPA_EMBEDDER_NAME

    se._cached_embedder.cache_clear()


def test_resolve_recluster_mode(monkeypatch) -> None:
    monkeypatch.delenv("TRANSLIP_DIARIZATION_RECLUSTER", raising=False)
    assert _resolve_recluster_mode() == "off"
    assert _resolve_recluster_mode("hdbscan") == "hdbscan"
    assert _resolve_recluster_mode("HDBSCAN") == "hdbscan"
    assert _resolve_recluster_mode("off") == "off"
    assert _resolve_recluster_mode("unknown") == "off"
    if importlib.util.find_spec("hdbscan") is not None:
        assert _resolve_recluster_mode("auto") == "hdbscan"
    else:
        assert _resolve_recluster_mode("auto") == "off"


def test_maybe_recluster_off_returns_input() -> None:
    matrix = np.eye(4, dtype=np.float32)
    cluster_ids = np.array([0, 0, 1, 1], dtype=np.int32)
    out, info = _maybe_recluster(matrix, cluster_ids, "off")
    assert info["recluster"] == "off"
    assert np.array_equal(out, cluster_ids)


def test_maybe_recluster_handles_missing_hdbscan(monkeypatch) -> None:
    matrix = np.random.default_rng(0).normal(size=(6, 16)).astype(np.float32)
    cluster_ids = np.array([0, 0, 1, 1, 2, 2], dtype=np.int32)

    import builtins

    real_import = builtins.__import__

    def _fake_import(name, *args, **kwargs):
        if name == "hdbscan":
            raise ImportError("mocked missing hdbscan")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _fake_import)

    out, info = _maybe_recluster(matrix, cluster_ids, "hdbscan")
    assert info["recluster"] == "off"
    assert info["recluster_error"] == "hdbscan-missing"
    assert np.array_equal(out, cluster_ids)


@pytest.mark.skipif(
    importlib.util.find_spec("hdbscan") is None,
    reason="hdbscan not installed; skipping reclustering integration probe",
)
def test_maybe_recluster_with_hdbscan_splits_well_separated_speakers() -> None:
    """Two tight clusters of ECAPA-sized embeddings must survive reclustering."""

    rng = np.random.default_rng(7)
    cluster_a = rng.normal(loc=0.0, scale=0.05, size=(6, 32)).astype(np.float32)
    cluster_b = rng.normal(loc=5.0, scale=0.05, size=(6, 32)).astype(np.float32)
    matrix = np.concatenate([cluster_a, cluster_b], axis=0)
    prior_ids = np.zeros(len(matrix), dtype=np.int32)
    prior_ids[len(cluster_a):] = 1

    refined, info = _maybe_recluster(matrix, prior_ids, "hdbscan")
    assert info["recluster"] in {"hdbscan", "hdbscan-skipped"}
    assert refined.shape == prior_ids.shape
    assert int(info["recluster_clusters_refined"]) >= 2


def test_stitch_noise_backfills_outliers() -> None:
    refined = np.array([-1, 0, 0, -1, 1, -1], dtype=np.int32)
    fallback = np.array([9, 9, 9, 9, 9, 9], dtype=np.int32)
    out = _stitch_noise(refined, fallback)
    assert -1 not in out.tolist()
    # First slot has no left neighbour -> inherits right neighbour (0).
    assert out[0] == 0
    # All-noise fallback uses the Agglomerative label for the *first* slot;
    # subsequent slots inherit through the already-filled left neighbour,
    # which is the documented propagation behaviour.
    all_noise = np.array([-1, -1], dtype=np.int32)
    fb = np.array([3, 7], dtype=np.int32)
    stitched = _stitch_noise(all_noise, fb)
    assert stitched.tolist() == [3, 3]


def test_nearest_labelled_boundaries() -> None:
    arr = np.array([-1, -1, 4, -1, -1], dtype=np.int32)
    assert _nearest_labelled(arr, 0, 1) == 4
    assert _nearest_labelled(arr, 4, -1) == 4
    assert _nearest_labelled(arr, 0, -1) is None
