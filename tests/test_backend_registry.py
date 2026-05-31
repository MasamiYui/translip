"""Tests for the generic backend registry and the per-domain registries.

These exercise the dispatch mechanism that replaced the hand-written
``if request.backend == ...`` factories. They must stay fast and must NOT pull
in heavy ML runtimes, so the per-domain registries are only checked for their
registered identifiers/metadata — never instantiated.
"""

from __future__ import annotations

import pytest

from translip.registry import BackendInfo, BackendRegistry


def test_register_and_create_forwards_kwargs():
    reg: BackendRegistry = BackendRegistry("demo")

    @reg.register("alpha", summary="Alpha")
    def _alpha(*, value):
        return ("alpha", value)

    assert reg.create("alpha", value=7) == ("alpha", 7)


def test_register_decorator_form():
    reg: BackendRegistry = BackendRegistry("demo")

    @reg.register("beta")
    def _beta(**kw):
        return kw.get("n")

    assert reg.create("beta", n=3) == 3


def test_aliases_resolve_to_canonical_identifier():
    reg: BackendRegistry = BackendRegistry("demo")

    @reg.register("canonical", aliases=("", "legacy"))
    def _canonical(**_):
        return "ok"

    assert reg.resolve("") == "canonical"
    assert reg.resolve("legacy") == "canonical"
    assert "" in reg
    assert "legacy" in reg
    assert reg.identifiers() == ["canonical"]


def test_unknown_backend_raises_helpful_key_error():
    reg: BackendRegistry = BackendRegistry("dubbing")

    @reg.register("real")
    def _real(**_):
        return 1

    with pytest.raises(KeyError) as exc:
        reg.create("imaginary")
    message = str(exc.value)
    assert "dubbing" in message
    assert "imaginary" in message


def test_duplicate_registration_is_rejected():
    reg: BackendRegistry = BackendRegistry("demo")

    @reg.register("x")
    def _x(**_):
        return 1

    with pytest.raises(ValueError):

        @reg.register("x")
        def _x2(**_):
            return 2


def test_info_and_introspection():
    reg: BackendRegistry = BackendRegistry("demo")

    @reg.register(
        "net",
        summary="needs internet",
        requires_network=True,
        metadata={"tier": "api"},
    )
    def _net(**_):
        return 1

    info = reg.get_info("net")
    assert isinstance(info, BackendInfo)
    assert info.identifier == "net"
    assert info.requires_network is True
    assert info.metadata == {"tier": "api"}
    with pytest.raises(KeyError):
        reg.get_info("missing")
    assert reg.identifiers() == ["net"]
    assert [i.identifier for i in reg.infos()] == ["net"]


def test_contains_rejects_non_strings():
    reg: BackendRegistry = BackendRegistry("demo")

    @reg.register("x")
    def _x(**_):
        return 1

    assert 123 not in reg
    assert None not in reg


def test_translation_registry_registers_expected_backends():
    from translip.translation.registry import TRANSLATION_BACKENDS

    assert set(TRANSLATION_BACKENDS.identifiers()) == {"local-m2m100", "siliconflow"}
    assert TRANSLATION_BACKENDS.get_info("siliconflow").requires_network is True
    assert TRANSLATION_BACKENDS.get_info("local-m2m100").requires_network is False


def test_tts_registry_registers_expected_backends():
    from translip.dubbing.registry import TTS_BACKENDS

    assert set(TTS_BACKENDS.identifiers()) == {"moss-tts-nano-onnx", "qwen3tts", "voxcpm2"}
    for ident in TTS_BACKENDS.identifiers():
        assert TTS_BACKENDS.get_info(ident).requires_reference_audio is True


def test_asr_registry_registers_expected_backends_with_fallback_alias():
    from translip.transcription.registry import ASR_BACKENDS, DEFAULT_ASR_BACKEND

    assert set(ASR_BACKENDS.identifiers()) == {"faster-whisper", "funasr"}
    assert DEFAULT_ASR_BACKEND == "faster-whisper"
    assert "" in ASR_BACKENDS
    assert ASR_BACKENDS.resolve("") == "faster-whisper"
    assert "totally-unknown" not in ASR_BACKENDS
