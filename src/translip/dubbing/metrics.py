from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from faster_whisper import WhisperModel

from ..speaker_embedding import (
    embedding_for_clip,
    load_speechbrain_classifier,
    read_audio_mono,
    resolve_speaker_device,
)
from ..transcription.asr import _compute_type, resolve_asr_device, resolve_faster_whisper_model_path
from ..translation.backend import canonical_language_code


@dataclass(slots=True)
class SegmentEvaluation:
    speaker_similarity: float | None
    speaker_status: str
    backread_text: str
    text_similarity: float
    intelligibility_status: str
    duration_ratio: float
    duration_status: str
    overall_status: str
    quality_flags: tuple[str, ...] = ()
    # Similarity to the speaker's stored prototype centroid (task-b), not just the
    # one reference clip this attempt cloned from. Catches a dub that matches a
    # possibly-atypical reference but not the character overall. "skipped" when no
    # centroid was supplied (e.g. voice-bank reference without a profile).
    speaker_similarity_centroid: float | None = None
    speaker_status_centroid: str = "skipped"


@lru_cache(maxsize=4)
def _load_backread_model(model_name: str, device: str, compute_type: str) -> WhisperModel:
    return WhisperModel(resolve_faster_whisper_model_path(model_name), device=device, compute_type=compute_type)


def evaluate_segment(
    *,
    reference_audio_path: Path,
    generated_audio_path: Path,
    target_text: str,
    target_lang: str,
    source_duration_sec: float,
    requested_device: str,
    backread_model_name: str,
    centroid_embedding: object | None = None,
) -> SegmentEvaluation:
    generated_waveform, generated_sample_rate = read_audio_mono(generated_audio_path)
    ref_embedding, gen_embedding = _speaker_embeddings(
        reference_audio_path=reference_audio_path,
        generated_waveform=generated_waveform,
        generated_sample_rate=generated_sample_rate,
        requested_device=requested_device,
    )
    speaker_similarity = (
        float(ref_embedding @ gen_embedding) if ref_embedding is not None and gen_embedding is not None else None
    )
    speaker_status = _speaker_status(speaker_similarity)
    # Second, reference-independent opinion: does the dub match the speaker's
    # prototype centroid? Reuses the embedding we already computed — no extra model.
    speaker_similarity_centroid: float | None = None
    speaker_status_centroid = "skipped"
    if centroid_embedding is not None and gen_embedding is not None:
        speaker_similarity_centroid = float(centroid_embedding @ gen_embedding)
        speaker_status_centroid = _speaker_status(speaker_similarity_centroid)
    backread_text = _backread_text(
        generated_audio_path,
        target_lang=target_lang,
        requested_device=requested_device,
        model_name=backread_model_name,
    )
    text_similarity = _text_similarity(target_text, backread_text)
    intelligibility_status = _intelligibility_status(text_similarity)
    generated_duration_sec = _duration_from_waveform(generated_waveform, generated_sample_rate)
    duration_ratio = generated_duration_sec / source_duration_sec if source_duration_sec > 0 else 0.0
    duration_status = _duration_status(duration_ratio)
    overall_status = _overall_status(
        speaker_status=speaker_status,
        intelligibility_status=intelligibility_status,
        duration_status=duration_status,
    )
    return SegmentEvaluation(
        speaker_similarity=speaker_similarity,
        speaker_status=speaker_status,
        backread_text=backread_text,
        text_similarity=text_similarity,
        intelligibility_status=intelligibility_status,
        duration_ratio=duration_ratio,
        duration_status=duration_status,
        overall_status=overall_status,
        speaker_similarity_centroid=speaker_similarity_centroid,
        speaker_status_centroid=speaker_status_centroid,
    )


def _speaker_embeddings(
    *,
    reference_audio_path: Path,
    generated_waveform,
    generated_sample_rate: int,
    requested_device: str,
) -> tuple[object | None, object | None]:
    """Embed the reference clip and the generated clip once, reused for both the
    per-attempt and the centroid cosine. Both are unit-normalized, so the dot
    product is cosine similarity."""
    device = resolve_speaker_device(requested_device)
    classifier = load_speechbrain_classifier(device)
    ref_embedding = _reference_embedding(reference_audio_path, device)
    gen_embedding = embedding_for_clip(classifier, generated_waveform, generated_sample_rate)
    return ref_embedding, gen_embedding


@lru_cache(maxsize=128)
def _reference_embedding(reference_audio_path: Path, device: str) -> object:
    classifier = load_speechbrain_classifier(device)
    ref_waveform, ref_sample_rate = read_audio_mono(reference_audio_path)
    return embedding_for_clip(classifier, ref_waveform, ref_sample_rate)


def _backread_text(
    audio_path: Path,
    *,
    target_lang: str,
    requested_device: str,
    model_name: str,
) -> str:
    device = resolve_asr_device(requested_device)
    model = _load_backread_model(model_name, device, _compute_type(device))
    language = canonical_language_code(target_lang)
    if language not in {"zh", "en", "ja"}:
        language = None
    segments, _ = model.transcribe(
        str(audio_path),
        language=language,
        vad_filter=False,
        beam_size=1,
        best_of=1,
        temperature=0.0,
        condition_on_previous_text=False,
    )
    return " ".join((segment.text or "").strip() for segment in segments).strip()


def _text_similarity(expected_text: str, actual_text: str) -> float:
    normalized_expected = _normalize_text(expected_text)
    normalized_actual = _normalize_text(actual_text)
    if not normalized_expected and not normalized_actual:
        return 1.0
    if not normalized_expected or not normalized_actual:
        return 0.0
    return float(difflib.SequenceMatcher(a=normalized_expected, b=normalized_actual).ratio())


def _normalize_text(text: str) -> str:
    lowered = text.strip().lower()
    lowered = re.sub(r"[^\w\u4e00-\u9fff\u3040-\u30ff]+", "", lowered)
    return lowered


def _speaker_status(score: float | None) -> str:
    if score is None:
        return "review"
    if score >= 0.45:
        return "passed"
    if score >= 0.25:
        return "review"
    return "failed"


def _intelligibility_status(score: float) -> str:
    if score >= 0.9:
        return "passed"
    if score >= 0.7:
        return "review"
    return "failed"


def _duration_status(duration_ratio: float) -> str:
    if 0.7 <= duration_ratio <= 1.35:
        return "passed"
    if 0.55 <= duration_ratio <= 1.65:
        return "review"
    return "failed"


def _overall_status(
    *,
    speaker_status: str,
    intelligibility_status: str,
    duration_status: str,
) -> str:
    statuses = {speaker_status, intelligibility_status, duration_status}
    if "failed" in statuses:
        return "failed"
    if "review" in statuses:
        return "review"
    return "passed"


def _duration_from_waveform(waveform, sample_rate: int) -> float:
    if sample_rate <= 0:
        return 0.0
    return float(len(waveform) / sample_rate)
