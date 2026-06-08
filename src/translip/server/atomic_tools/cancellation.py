"""Unified cancellation contract for atomic-tool adapters (ATOM-3).

The job manager hands every adapter an ``on_progress`` callback and attaches a
cancellation predicate to it via :func:`attach_cancel_checker`. Adapters that
shell out to a subprocess pass :func:`cancel_checker` to
``run_stage_command(should_cancel=...)`` so the child is terminated when the job
is cancelled — the exact same ``Callable[[], bool]`` contract the pipeline
orchestrator uses (see ARCH-8). In-process adapters are cancelled cooperatively
the next time they call ``on_progress`` (which raises ``AtomicJobCancelled``).

Centralising the lookup here removes the fragile, duplicated
``getattr(on_progress, "is_cancelled", None)`` literal that each shelling adapter
previously carried — a new adapter can wire cancellation correctly with one call
and cannot silently forget the magic attribute name.
"""

from __future__ import annotations

from typing import Any, Callable

# Attribute name under which the cancellation predicate is stashed on on_progress.
CANCEL_ATTR = "should_cancel"


def attach_cancel_checker(on_progress: Any, predicate: Callable[[], bool]) -> None:
    """Attach a ``() -> bool`` cancellation predicate to an on_progress callback."""
    setattr(on_progress, CANCEL_ATTR, predicate)


def cancel_checker(on_progress: Any) -> Callable[[], bool] | None:
    """Return the cancellation predicate for a shelling adapter, or None.

    Pass the result straight to ``run_stage_command(should_cancel=...)``. Returns
    None when no predicate was attached (e.g. an adapter invoked outside the job
    manager), which ``run_stage_command`` treats as "not cancellable".
    """
    checker = getattr(on_progress, CANCEL_ATTR, None)
    return checker if callable(checker) else None
