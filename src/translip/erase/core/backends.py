"""Inpainting backends that fill a masked subtitle region in a batch of frames.

Every backend implements ``__call__(frames, mask) -> frames`` where ``frames``
is a list of HxWx3 BGR uint8 arrays and ``mask`` is a single HxW ``{0, 255}``
union mask for the batch. Backends return new frames with the masked region
filled; pixels outside the mask are always left untouched.

Two correctness fixes over the upstream video-subtitle-remover code:
  * compositing is done strictly inside the mask at full resolution (upstream
    hard-pastes the whole band, which alters non-subtitle pixels), and
  * color order is handled explicitly (net I/O is RGB, frames are BGR), instead
    of relying on a compensating double cvtColor.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import torch

from ..utils.devices import empty_cache
from .lama_util import pad_to_modulo, to_chw_float
from .masks import get_inpaint_bands
from .sttn_network import DET_INPUT_SIZE, InpaintGenerator


class InpaintBackend:
    """Base class: subclasses implement ``__call__`` and expose ``name``."""

    name: str = "base"

    def __call__(self, frames: list[np.ndarray], mask: np.ndarray) -> list[np.ndarray]:
        raise NotImplementedError


class OpenCVBackend(InpaintBackend):
    """cv2 Telea inpainting — per-frame, zero extra deps, always available."""

    name = "opencv"

    def __init__(self, *, radius: int = 3) -> None:
        self.radius = radius

    def __call__(self, frames: list[np.ndarray], mask: np.ndarray) -> list[np.ndarray]:
        return [cv2.inpaint(frame, mask, self.radius, cv2.INTER_LINEAR) for frame in frames]


class SttnBackend(InpaintBackend):
    """STTN video inpainting with temporal neighbor/reference attention."""

    name = "sttn"

    def __init__(
        self,
        *,
        device: torch.device,
        model_path: Path,
        neighbor_stride: int = 5,
        reference_length: int = 10,
    ) -> None:
        self.device = device
        self.neighbor_stride = max(1, neighbor_stride)
        self.reference_length = max(1, reference_length)
        self.model_w, self.model_h = DET_INPUT_SIZE
        model = InpaintGenerator()
        model.load_state_dict(torch.load(model_path, map_location="cpu", weights_only=False)["netG"])
        self.model = model.to(device).eval()

    def __call__(self, frames: list[np.ndarray], mask: np.ndarray) -> list[np.ndarray]:
        height, width = mask.shape[:2]
        split_h = int(height * 5 / 9) if height > width else int(width * 5 / 18)
        return _process_banded(frames, mask, split_h, self._fill_band)

    def _fill_band(self, crops: list[np.ndarray], mask_crop: np.ndarray) -> list[np.ndarray]:
        band_h, band_w = crops[0].shape[:2]
        resized = [cv2.resize(c, (self.model_w, self.model_h)) for c in crops]
        mask_resized = cv2.resize(mask_crop, (self.model_w, self.model_h), interpolation=cv2.INTER_NEAREST)
        filled = self._inpaint(resized, mask_resized)
        return [cv2.resize(f, (band_w, band_h)) for f in filled]

    @torch.no_grad()
    def _inpaint(self, frames: list[np.ndarray], mask: np.ndarray) -> list[np.ndarray]:
        count = len(frames)
        rgb = np.stack([cv2.cvtColor(f, cv2.COLOR_BGR2RGB) for f in frames], axis=0)
        feats = torch.from_numpy(rgb).permute(0, 3, 1, 2).contiguous().float().div(255).mul(2).sub(1)
        feats = feats.unsqueeze(0).to(self.device)  # [1, T, 3, h, w] in [-1, 1]
        mask_t = (torch.from_numpy(mask).float().div(255) > 0.5).float()
        mask_t = mask_t.view(1, 1, 1, *mask.shape).repeat(1, count, 1, 1, 1).to(self.device)

        encoded = self.model.encoder((feats * (1 - mask_t)).view(count, 3, self.model_h, self.model_w))
        _, channels, feat_h, feat_w = encoded.size()
        encoded = encoded.view(1, count, channels, feat_h, feat_w)

        comp: list[np.ndarray | None] = [None] * count
        for pivot in range(0, count, self.neighbor_stride):
            neighbor_ids = list(range(max(0, pivot - self.neighbor_stride), min(count, pivot + self.neighbor_stride + 1)))
            ref_ids = [i for i in range(0, count, self.reference_length) if i not in neighbor_ids]
            selected = neighbor_ids + ref_ids
            pred_feat = self.model.infer(encoded[0, selected])
            pred_img = torch.tanh(self.model.decoder(pred_feat[: len(neighbor_ids)]))
            pred_img = ((pred_img + 1) / 2).clamp(0, 1).cpu().permute(0, 2, 3, 1).numpy() * 255
            for i, idx in enumerate(neighbor_ids):
                frame_pred = pred_img[i]
                comp[idx] = frame_pred if comp[idx] is None else comp[idx] * 0.5 + frame_pred * 0.5
        empty_cache(self.device)
        return [cv2.cvtColor(np.clip(c, 0, 255).astype(np.uint8), cv2.COLOR_RGB2BGR) for c in comp]


class LamaBackend(InpaintBackend):
    """big-LaMa single-frame inpainting (TorchScript)."""

    name = "lama"

    def __init__(self, *, device: torch.device, model_path: Path, mini_batch: int = 4) -> None:
        self.device = device
        self.mini_batch = max(1, mini_batch)
        self.model = torch.jit.load(str(model_path), map_location="cpu").to(device).eval()

    def __call__(self, frames: list[np.ndarray], mask: np.ndarray) -> list[np.ndarray]:
        height, width = mask.shape[:2]
        split_h = int(width * 3 / 16)
        return _process_banded(frames, mask, split_h, self._fill_band)

    def _fill_band(self, crops: list[np.ndarray], mask_crop: np.ndarray) -> list[np.ndarray]:
        band_h, band_w = crops[0].shape[:2]
        results: list[np.ndarray] = []
        for start in range(0, len(crops), self.mini_batch):
            batch = crops[start : start + self.mini_batch]
            results.extend(self._inpaint_batch(batch, mask_crop, band_h, band_w))
        return results

    @torch.inference_mode()
    def _inpaint_batch(self, crops: list[np.ndarray], mask_crop: np.ndarray, band_h: int, band_w: int) -> list[np.ndarray]:
        # Feed RGB (the LaMa graph expects RGB); convert results back to BGR.
        imgs = np.stack([pad_to_modulo(to_chw_float(cv2.cvtColor(c, cv2.COLOR_BGR2RGB))) for c in crops])
        mask_chw = pad_to_modulo(to_chw_float(mask_crop))
        masks = np.repeat(mask_chw[np.newaxis, ...], len(crops), axis=0)
        img_t = torch.from_numpy(imgs).to(self.device)
        mask_t = ((torch.from_numpy(masks) > 0) * 1).to(self.device)
        out = self.model(img_t, mask_t)
        out = out.permute(0, 2, 3, 1).detach().cpu().numpy()
        out = np.clip(out * 255, 0, 255).astype(np.uint8)
        empty_cache(self.device)
        return [cv2.cvtColor(frame[:band_h, :band_w], cv2.COLOR_RGB2BGR) for frame in out]


def _process_banded(
    frames: list[np.ndarray],
    mask: np.ndarray,
    split_h: int,
    fill_band,
) -> list[np.ndarray]:
    """Crop the masked vertical band(s), inpaint, composite back inside the mask."""
    height, width = mask.shape[:2]
    bands = get_inpaint_bands(width, height, max(1, split_h), mask)
    out = [frame.copy() for frame in frames]
    if not bands:
        return out
    mask_bool = mask > 127
    for ymin, ymax in bands:
        crops = [frame[ymin:ymax, :, :] for frame in frames]
        filled = fill_band(crops, mask[ymin:ymax, :])
        region_mask = mask_bool[ymin:ymax, :, np.newaxis]
        for frame_out, band_img in zip(out, filled):
            region = frame_out[ymin:ymax, :, :]
            frame_out[ymin:ymax, :, :] = np.where(region_mask, band_img, region)
    return out


__all__ = ["InpaintBackend", "OpenCVBackend", "SttnBackend", "LamaBackend"]
