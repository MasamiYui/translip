from __future__ import annotations

import os
from functools import lru_cache

import torch
from transformers import M2M100ForConditionalGeneration, M2M100Tokenizer

from ..config import CACHE_ROOT
from ..exceptions import BackendUnavailableError
from .backend import BackendSegmentInput, BackendSegmentOutput, m2m100_language_code


def resolve_translation_device(requested_device: str) -> str:
    mps_available = bool(getattr(torch.backends, "mps", None) and torch.backends.mps.is_available())
    if requested_device == "cuda":
        return "cuda" if torch.cuda.is_available() else "cpu"
    if requested_device == "mps":
        return "mps" if mps_available else "cpu"
    if requested_device == "auto":
        if torch.cuda.is_available():
            return "cuda"
        if mps_available:
            return "mps"
        return "cpu"
    return "cpu"


@lru_cache(maxsize=4)
def _load_m2m100(model_name: str, device: str) -> tuple[M2M100Tokenizer, M2M100ForConditionalGeneration]:
    cache_dir = CACHE_ROOT / "transformers"
    tokenizer = M2M100Tokenizer.from_pretrained(model_name, cache_dir=str(cache_dir))
    model = M2M100ForConditionalGeneration.from_pretrained(model_name, cache_dir=str(cache_dir))
    model.eval()
    if device == "mps":
        os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
    model.to(device)
    return tokenizer, model


class M2M100Backend:
    backend_name = "local-m2m100"

    def __init__(self, *, model_name: str, requested_device: str) -> None:
        self.model_name = model_name
        self.requested_device = requested_device
        self.resolved_model = model_name
        self.resolved_device = resolve_translation_device(requested_device)

    def translate_batch(
        self,
        *,
        items: list[BackendSegmentInput],
        source_lang: str,
        target_lang: str,
    ) -> list[BackendSegmentOutput]:
        if not items:
            return []
        try:
            return self._translate_with_device(
                items=items,
                source_lang=source_lang,
                target_lang=target_lang,
                device=self.resolved_device,
            )
        except Exception as exc:
            if self.resolved_device == "mps":
                self.resolved_device = "cpu"
                return self._translate_with_device(
                    items=items,
                    source_lang=source_lang,
                    target_lang=target_lang,
                    device="cpu",
                )
            raise BackendUnavailableError(f"M2M100 translation failed: {exc}") from exc

    def _translate_with_device(
        self,
        *,
        items: list[BackendSegmentInput],
        source_lang: str,
        target_lang: str,
        device: str,
    ) -> list[BackendSegmentOutput]:
        tokenizer, model = _load_m2m100(self.model_name, device)
        tokenizer.src_lang = m2m100_language_code(source_lang)
        encoded = tokenizer(
            [item.source_text for item in items],
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=512,
        )
        encoded = {key: value.to(device) for key, value in encoded.items()}
        with torch.inference_mode():
            generated = model.generate(
                **encoded,
                forced_bos_token_id=tokenizer.get_lang_id(m2m100_language_code(target_lang)),
                max_new_tokens=256,
            )
        decoded = tokenizer.batch_decode(generated, skip_special_tokens=True)
        return [
            BackendSegmentOutput(
                segment_id=item.segment_id,
                target_text=text.strip(),
                metadata={"device": device},
            )
            for item, text in zip(items, decoded, strict=True)
        ]
