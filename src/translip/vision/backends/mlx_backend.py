"""mlx-vlm backend (Apple Silicon, in-process Metal inference).

No per-inference timeout here: the model runs synchronously in this process and
cannot be interrupted cleanly — hang protection is the parent's job (the
orchestrator/job manager SIGTERMs the whole subprocess on cancel).
"""
from __future__ import annotations

import os
from pathlib import Path

from ..config import VisionSettings


class MlxVisionBackend:
    backend_name = "mlx"

    def __init__(self, *, settings: VisionSettings, model_id: str) -> None:
        self._settings = settings
        self.model_id = model_id
        self._model = None
        self._processor = None
        self._config = None

    def load(self) -> None:
        # Confine HF downloads to translip's cache unless the user pointed
        # VISION_HF_CACHE elsewhere; honor an externally-set HF_HUB_CACHE.
        if self._settings.hf_cache_explicit or "HF_HUB_CACHE" not in os.environ:
            os.environ["HF_HUB_CACHE"] = self._settings.hf_cache
        if self._settings.local_models_only:
            os.environ["HF_HUB_OFFLINE"] = "1"
        try:
            from mlx_vlm import load as mlx_load
            from mlx_vlm.utils import load_config
        except ImportError as exc:  # pragma: no cover - exercised on real installs
            raise ImportError(
                "mlx-vlm is required for the 'mlx' vision backend. "
                "Install it with: uv sync --extra vision"
            ) from exc
        # If the model is already fully cached, hand mlx-vlm the resolved local
        # *path* instead of the repo id: get_model_path() skips snapshot_download
        # for a path that exists, so we never hit huggingface_hub's network
        # revision check — which it runs even on a cache hit and crashes when the
        # Hub is unreachable (firewall/offline). A missing or partial snapshot
        # resolves to None and falls through to the normal online download.
        target = self._resolve_cached_path() or self.model_id
        self._model, self._processor = mlx_load(target)
        self._config = load_config(target)

    def _resolve_cached_path(self) -> str | None:
        """Return the local model dir if fully cached (never touches network).

        Probes the HF cache with ``local_files_only``; any failure (not cached,
        partial download, hub error) returns None so the caller falls back to
        the repo id and the normal download path.
        """
        if Path(self.model_id).exists():
            return self.model_id  # already a filesystem path
        try:
            from huggingface_hub import snapshot_download
        except ImportError:
            return None
        try:
            return snapshot_download(
                self.model_id,
                local_files_only=True,
                cache_dir=os.environ.get("HF_HUB_CACHE") or None,
            )
        except Exception:
            return None

    def chat(self, images: list[Path], prompt: str) -> str:
        if self._model is None:
            raise RuntimeError("backend not loaded; call load() first")
        from mlx_vlm import generate
        from mlx_vlm.prompt_utils import apply_chat_template

        formatted = apply_chat_template(self._processor, self._config, prompt, num_images=len(images))
        result = generate(
            self._model,
            self._processor,
            formatted,
            [str(path) for path in images],
            max_tokens=self._settings.max_new_tokens,
            temperature=self._settings.temperature,
            verbose=False,
        )
        return result.text if hasattr(result, "text") else str(result)

    def close(self) -> None:
        # The subprocess exit frees Metal memory; drop references for symmetry.
        self._model = None
        self._processor = None
        self._config = None


__all__ = ["MlxVisionBackend"]
