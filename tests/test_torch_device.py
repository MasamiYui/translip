from __future__ import annotations

import logging
import types

import pytest

import torch

from translip.utils.torch_device import resolve_torch_device


@pytest.fixture
def patched_torch(monkeypatch):
    """Set cuda/mps availability on the torch module the helper imports."""

    def _apply(*, cuda: bool, mps: bool, mps_attr: bool = True):
        monkeypatch.setattr(torch.cuda, "is_available", lambda: cuda)
        if mps_attr:
            fake_mps = types.SimpleNamespace(is_available=lambda: mps)
            monkeypatch.setattr(torch.backends, "mps", fake_mps, raising=False)
        else:
            # Simulate a torch build without an MPS backend; the helper guards
            # with ``getattr(torch.backends, "mps", None) is not None``.
            monkeypatch.setattr(torch.backends, "mps", None, raising=False)

    return _apply


def test_auto_prefers_cuda(patched_torch):
    patched_torch(cuda=True, mps=True)
    assert resolve_torch_device("auto") == "cuda"


def test_auto_falls_back_to_mps_when_no_cuda(patched_torch):
    patched_torch(cuda=False, mps=True)
    assert resolve_torch_device("auto") == "mps"


def test_auto_falls_back_to_cpu_when_neither(patched_torch):
    patched_torch(cuda=False, mps=False)
    assert resolve_torch_device("auto") == "cpu"


def test_explicit_cuda_unavailable_falls_back_to_cpu(patched_torch):
    patched_torch(cuda=False, mps=True)
    assert resolve_torch_device("cuda") == "cpu"


def test_explicit_mps_unavailable_falls_back_to_cpu(patched_torch):
    patched_torch(cuda=True, mps=False)
    assert resolve_torch_device("mps") == "cpu"


def test_explicit_cpu_returns_cpu(patched_torch):
    patched_torch(cuda=True, mps=True)
    assert resolve_torch_device("cpu") == "cpu"


def test_unknown_request_returns_cpu(patched_torch):
    patched_torch(cuda=True, mps=True)
    assert resolve_torch_device("bogus") == "cpu"


def test_explicit_cuda_available_returns_cuda(patched_torch):
    patched_torch(cuda=True, mps=False)
    assert resolve_torch_device("cuda") == "cuda"


def test_explicit_mps_available_returns_mps(patched_torch):
    patched_torch(cuda=False, mps=True)
    assert resolve_torch_device("mps") == "mps"


def test_mps_attr_missing_is_guarded(patched_torch):
    # torch builds without an ``mps`` backend must not raise and must fall to CPU.
    patched_torch(cuda=False, mps=False, mps_attr=False)
    assert resolve_torch_device("mps") == "cpu"
    assert resolve_torch_device("auto") == "cpu"


def test_logger_warns_on_unavailable_cuda(patched_torch, caplog):
    patched_torch(cuda=False, mps=False)
    logger = logging.getLogger("test_torch_device")
    with caplog.at_level(logging.WARNING, logger="test_torch_device"):
        assert resolve_torch_device("cuda", logger=logger) == "cpu"
    assert any("CUDA" in rec.message for rec in caplog.records)


def test_no_logger_is_silent(patched_torch, caplog):
    patched_torch(cuda=False, mps=False)
    with caplog.at_level(logging.WARNING):
        assert resolve_torch_device("cuda") == "cpu"
    assert caplog.records == []
