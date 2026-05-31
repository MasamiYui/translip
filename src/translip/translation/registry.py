"""Registry of translation backends.

Adding a translation backend is a single registration here: provide a factory
that lazily imports and constructs the implementation. Factories take explicit
keyword args (model name, device, API settings) rather than a whole
``TranslationRequest`` so the script runner and the subtitle runner can share
one dispatch path instead of duplicating the ``if/elif`` chain verbatim.
Unknown keyword args are ignored (``**_``) so callers may forward a superset.
"""

from __future__ import annotations

from ..config import DEFAULT_TRANSLATION_LOCAL_MODEL
from ..registry import BackendRegistry

TRANSLATION_BACKENDS: BackendRegistry = BackendRegistry("translation")


@TRANSLATION_BACKENDS.register(
    "local-m2m100",
    summary="Local M2M100 model (offline, no network required).",
)
def _build_m2m100(*, local_model: str = DEFAULT_TRANSLATION_LOCAL_MODEL, device: str = "auto", **_):
    from .m2m100_backend import M2M100Backend

    return M2M100Backend(model_name=local_model, requested_device=device)


@TRANSLATION_BACKENDS.register(
    "siliconflow",
    summary="SiliconFlow chat-completions API (LLM translation).",
    requires_network=True,
)
def _build_siliconflow(
    *, api_model: str | None = None, api_base_url: str | None = None, device: str = "auto", **_
):
    from .siliconflow_backend import SiliconFlowBackend

    return SiliconFlowBackend(
        model_name=api_model,
        base_url=api_base_url,
        requested_device=device,
    )


__all__ = ["TRANSLATION_BACKENDS"]
