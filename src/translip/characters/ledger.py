from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..pipeline.manifest import now_iso
from ..quality.audio_signature import pitch_class_distance, voice_signature
from ..utils.files import ensure_directory


@dataclass(slots=True)
class CharacterLedgerRequest:
    profiles_path: Path | str
    task_d_report_paths: list[Path | str]
    output_dir: Path | str
    target_lang: str = "en"

    def normalized(self) -> "CharacterLedgerRequest":
        return CharacterLedgerRequest(
            profiles_path=Path(self.profiles_path).expanduser().resolve(),
            task_d_report_paths=[Path(path).expanduser().resolve() for path in self.task_d_report_paths],
            output_dir=Path(self.output_dir).expanduser().resolve(),
            target_lang=self.target_lang,
        )


@dataclass(slots=True)
class CharacterLedgerArtifacts:
    ledger_path: Path
    report_path: Path
    manifest_path: Path


@dataclass(slots=True)
class CharacterLedgerResult:
    request: CharacterLedgerRequest
    artifacts: CharacterLedgerArtifacts
    ledger: dict[str, Any]
    manifest: dict[str, Any]


def build_character_ledger(request: CharacterLedgerRequest) -> CharacterLedgerResult:
    normalized = _validate_request(request)
    started_at = now_iso()
    started_monotonic = time.monotonic()
    output_dir = ensure_directory(Path(normalized.output_dir))
    ledger_path = output_dir / f"character_ledger.{normalized.target_lang}.json"
    report_path = output_dir / f"character_ledger_report.{normalized.target_lang}.md"
    manifest_path = output_dir / "character-ledger-manifest.json"

    profiles = _read_json(Path(normalized.profiles_path))
    reports = [_read_json(Path(path)) for path in normalized.task_d_report_paths]
    report_by_speaker = {
        str(report.get("speaker_id") or ""): report
        for report in reports
        if isinstance(report, dict) and report.get("speaker_id")
    }
    characters = [
        _character_payload(index=index, profile=profile, report=report_by_speaker.get(str(profile.get("speaker_id") or ""), {}))
        for index, profile in enumerate(_profiles(profiles), start=1)
    ]
    ledger = {
        "version": "character-ledger-v1",
        "created_at": now_iso(),
        "target_lang": normalized.target_lang,
        "input": {
            "profiles_path": str(normalized.profiles_path),
            "task_d_report_paths": [str(path) for path in normalized.task_d_report_paths],
        },
        "stats": _stats(characters),
        "characters": characters,
    }
    _write_json(ledger_path, ledger)
    report_path.write_text(_markdown_report(ledger), encoding="utf-8")
    manifest = {
        "status": "succeeded",
        "input": ledger["input"],
        "artifacts": {
            "ledger": str(ledger_path),
            "report": str(report_path),
        },
        "stats": ledger["stats"],
        "timing": {
            "started_at": started_at,
            "finished_at": now_iso(),
            "elapsed_sec": round(time.monotonic() - started_monotonic, 3),
        },
        "error": None,
    }
    _write_json(manifest_path, manifest)
    return CharacterLedgerResult(
        request=normalized,
        artifacts=CharacterLedgerArtifacts(
            ledger_path=ledger_path,
            report_path=report_path,
            manifest_path=manifest_path,
        ),
        ledger=ledger,
        manifest=manifest,
    )


def _validate_request(request: CharacterLedgerRequest) -> CharacterLedgerRequest:
    normalized = request.normalized()
    if not Path(normalized.profiles_path).exists():
        raise FileNotFoundError(f"Speaker profiles file does not exist: {normalized.profiles_path}")
    for path in normalized.task_d_report_paths:
        if not Path(path).exists():
            raise FileNotFoundError(f"Task D report file does not exist: {path}")
    return normalized


def _profiles(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        profile
        for profile in payload.get("profiles", [])
        if isinstance(profile, dict) and profile.get("speaker_id")
    ]


def _character_payload(*, index: int, profile: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    speaker_id = str(profile.get("speaker_id") or report.get("speaker_id") or "")
    reference_path = _reference_path(profile=profile, report=report)
    reference_signature = _safe_signature(reference_path)
    segment_rows = [row for row in report.get("segments", []) if isinstance(row, dict)]
    generated = [_segment_voice(row=row, expected=reference_signature) for row in segment_rows]
    generated = [row for row in generated if row is not None]
    speaker_failed_count = sum(1 for row in segment_rows if str(row.get("speaker_status") or "") == "failed")
    overall_failed_count = sum(1 for row in segment_rows if str(row.get("overall_status") or "") == "failed")
    voice_mismatch_count = sum(1 for row in generated if row.get("voice_consistency_status") == "failed")
    risk_flags = _risk_flags(
        reference_signature=reference_signature,
        segment_count=len(segment_rows),
        speaker_failed_count=speaker_failed_count,
        voice_mismatch_count=voice_mismatch_count,
    )
    return {
        "character_id": f"char_{index:04d}",
        "display_name": str(profile.get("display_name") or profile.get("source_label") or speaker_id),
        "speaker_ids": [speaker_id],
        "source_label": profile.get("source_label"),
        "profile_id": profile.get("profile_id"),
        "reference_path": reference_path,
        "voice_signature": reference_signature,
        "stats": {
            "segment_count": len(segment_rows),
            "speaker_failed_count": speaker_failed_count,
            "overall_failed_count": overall_failed_count,
            "voice_mismatch_count": voice_mismatch_count,
            "speaker_failed_ratio": round(speaker_failed_count / len(segment_rows), 4) if segment_rows else 0.0,
        },
        "risk_flags": risk_flags,
        "review_status": _review_status(risk_flags),
        "generated_voice_samples": generated[:20],
    }


def _reference_path(*, profile: dict[str, Any], report: dict[str, Any]) -> str | None:
    report_reference = str(report.get("reference", {}).get("path") or "").strip()
    if report_reference:
        return str(Path(report_reference).expanduser().resolve())
    for raw in profile.get("reference_clips", []):
        if isinstance(raw, dict) and raw.get("path"):
            return str(Path(str(raw.get("path"))).expanduser().resolve())
    return None


def _safe_signature(path: str | None) -> dict[str, Any]:
    if not path:
        return {"path": None, "duration_sec": 0.0, "rms": 0.0, "pitch_hz": None, "pitch_class": "unknown"}
    candidate = Path(path)
    if not candidate.exists():
        return {"path": path, "duration_sec": 0.0, "rms": 0.0, "pitch_hz": None, "pitch_class": "unknown"}
    return voice_signature(candidate).to_payload()


def _segment_voice(*, row: dict[str, Any], expected: dict[str, Any]) -> dict[str, Any] | None:
    audio_path = str(row.get("audio_path") or "").strip()
    if not audio_path:
        return None
    path = Path(audio_path).expanduser().resolve()
    if not path.exists():
        return None
    signature = voice_signature(path).to_payload()
    status = _voice_consistency_status(
        expected_pitch_class=str(expected.get("pitch_class") or "unknown"),
        generated_pitch_class=str(signature.get("pitch_class") or "unknown"),
    )
    return {
        "segment_id": row.get("segment_id"),
        "audio_path": str(path),
        "pitch_hz": signature["pitch_hz"],
        "pitch_class": signature["pitch_class"],
        "voice_consistency_status": status,
    }


def _voice_consistency_status(*, expected_pitch_class: str, generated_pitch_class: str) -> str:
    distance = pitch_class_distance(expected_pitch_class, generated_pitch_class)
    if distance is None:
        return "review"
    if distance >= 2:
        return "failed"
    if distance == 1:
        return "review"
    return "passed"


def _risk_flags(
    *,
    reference_signature: dict[str, Any],
    segment_count: int,
    speaker_failed_count: int,
    voice_mismatch_count: int,
) -> list[str]:
    flags: list[str] = []
    if str(reference_signature.get("pitch_class") or "unknown") == "unknown":
        flags.append("reference_voice_unknown")
    if segment_count > 0 and speaker_failed_count / segment_count >= 0.2:
        flags.append("speaker_similarity_failed")
    if voice_mismatch_count > 0:
        flags.append("pitch_class_drift")
    return flags


def _review_status(risk_flags: list[str]) -> str:
    if "reference_voice_unknown" in risk_flags and len(risk_flags) > 1:
        return "blocked"
    if risk_flags:
        return "review"
    return "passed"


def _stats(characters: list[dict[str, Any]]) -> dict[str, Any]:
    review_count = sum(1 for row in characters if row.get("review_status") == "review")
    blocked_count = sum(1 for row in characters if row.get("review_status") == "blocked")
    mismatch_count = sum(int(row.get("stats", {}).get("voice_mismatch_count") or 0) for row in characters)
    return {
        "character_count": len(characters),
        "review_count": review_count,
        "blocked_count": blocked_count,
        "voice_mismatch_count": mismatch_count,
    }


def _markdown_report(ledger: dict[str, Any]) -> str:
    lines = [
        "# Character Ledger Report",
        "",
        f"- version: `{ledger.get('version')}`",
        f"- target_lang: `{ledger.get('target_lang')}`",
        f"- character_count: `{ledger.get('stats', {}).get('character_count', 0)}`",
        f"- voice_mismatch_count: `{ledger.get('stats', {}).get('voice_mismatch_count', 0)}`",
        "",
        "| character | speakers | pitch | status | risks |",
        "| --- | --- | --- | --- | --- |",
    ]
    for character in ledger.get("characters", []):
        voice = character.get("voice_signature", {})
        lines.append(
            "| {character} | {speakers} | {pitch} | {status} | {risks} |".format(
                character=character.get("character_id"),
                speakers=", ".join(character.get("speaker_ids", [])),
                pitch=voice.get("pitch_class", "unknown"),
                status=character.get("review_status"),
                risks=", ".join(character.get("risk_flags", [])) or "-",
            )
        )
    return "\n".join(lines) + "\n"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


__all__ = ["CharacterLedgerArtifacts", "CharacterLedgerRequest", "CharacterLedgerResult", "build_character_ledger"]
