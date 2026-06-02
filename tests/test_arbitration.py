from __future__ import annotations

import pytest

from translip.exceptions import BackendUnavailableError
from translip.transcription.arbitration import ChatArbitrator, make_arbitrator
from translip.transcription.ocr_correction import ArbitrationRequest


def _response(content: str) -> dict:
    return {"choices": [{"message": {"content": content}}]}


def _request() -> ArbitrationRequest:
    return ArbitrationRequest(
        segment_id="s1", asr_text="要恨就恨", ocr_text="要狠就狠", start=0.0, end=1.0, speaker_label="SPEAKER_00"
    )


def _arbitrator(monkeypatch, responses: list[dict]):
    arb = make_arbitrator("deepseek", api_key="test-key", max_retries=0)
    calls: list[dict] = []

    def fake_post(url: str, payload: dict) -> dict:
        calls.append(payload)
        return responses[len(calls) - 1]

    monkeypatch.setattr(arb, "_post_json", fake_post)
    return arb, calls


def test_make_arbitrator_uses_deepseek_provider() -> None:
    arb = make_arbitrator("deepseek", api_key="k")
    assert arb.base_url == "https://api.deepseek.com"
    assert arb.model_name == "deepseek-v4-pro"


def test_parses_valid_verdict(monkeypatch) -> None:
    arb, calls = _arbitrator(monkeypatch, [_response('{"decision":"use_ocr","text":"要狠就狠","reason":"形近"}')])
    verdict = arb(_request())
    assert verdict is not None
    assert verdict.decision == "use_ocr"
    assert verdict.text == "要狠就狠"
    assert verdict.reason == "形近"
    # Prompt carries both sources.
    user_msg = calls[0]["messages"][1]["content"]
    assert "要恨就恨" in user_msg and "要狠就狠" in user_msg


def test_invalid_decision_returns_none(monkeypatch) -> None:
    arb, _ = _arbitrator(monkeypatch, [_response('{"decision":"banana","text":"x","reason":"?"}')])
    assert arb(_request()) is None


def test_malformed_json_returns_none(monkeypatch) -> None:
    arb, _ = _arbitrator(monkeypatch, [_response("not json at all")])
    assert arb(_request()) is None


def test_memoizes_identical_text_pairs(monkeypatch) -> None:
    arb, calls = _arbitrator(
        monkeypatch,
        [_response('{"decision":"use_asr","text":"要恨就恨","reason":"r"}')],
    )
    first = arb(ArbitrationRequest("s1", "要恨就恨", "要狠就狠", 0.0, 1.0, None))
    second = arb(ArbitrationRequest("s2", "要恨就恨", "要狠就狠", 9.0, 10.0, None))
    assert first is second
    assert len(calls) == 1  # second call served from cache, no extra HTTP


def test_missing_api_key_raises(monkeypatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with pytest.raises(BackendUnavailableError):
        make_arbitrator("deepseek")


def test_unknown_mode_raises() -> None:
    with pytest.raises(ValueError):
        make_arbitrator("nope", api_key="k")
