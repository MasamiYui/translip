from __future__ import annotations

from translip.server.atomic_tools.cancellation import (
    CANCEL_ATTR,
    attach_cancel_checker,
    cancel_checker,
)


def test_attach_and_read_cancel_checker_round_trip() -> None:
    state = {"cancelled": False}

    def on_progress(percent: float, step: str | None = None) -> None:
        return None

    attach_cancel_checker(on_progress, lambda: state["cancelled"])
    checker = cancel_checker(on_progress)
    assert checker is not None
    assert checker() is False
    state["cancelled"] = True
    assert checker() is True
    assert getattr(on_progress, CANCEL_ATTR) is checker


def test_cancel_checker_none_when_not_attached() -> None:
    def on_progress(percent: float, step: str | None = None) -> None:
        return None

    assert cancel_checker(on_progress) is None


def test_cancel_checker_none_when_attribute_not_callable() -> None:
    def on_progress(percent: float, step: str | None = None) -> None:
        return None

    setattr(on_progress, CANCEL_ATTR, "not-callable")
    assert cancel_checker(on_progress) is None
