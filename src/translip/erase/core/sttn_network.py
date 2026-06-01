"""STTN (Spatial-Temporal Transformer Network) generator — inference only.

Ported from video-subtitle-remover ``backend/inpaint/sttn/network_sttn.py``,
itself derived from researchmm/STTN (Zeng et al., ECCV 2020), both Apache-2.0.

This is a clean-room inference port: the training-only ``Discriminator`` /
spectral-norm and the (no-op) attention ``masked_fill`` of the upstream code are
dropped — upstream applies ``masked_fill`` *non-in-place* and discards the
result, so the published ``netG`` weights were effectively trained without
attention masking. Masking instead happens by feeding ``frame * (1 - mask)`` to
the encoder and compositing only inside the mask afterwards (see backends.py).

Submodule attribute names (``encoder`` / ``transformer`` / ``decoder`` and the
``query/key/value_embedding`` + ``output_linear`` + ``feed_forward`` children)
are preserved verbatim so the upstream ``netG`` ``state_dict`` loads unchanged.
"""
from __future__ import annotations

import math

import torch
import torch.nn as nn
import torch.nn.functional as F

# (width, height) attention patch sizes per head for the 432x240 "det" weights.
DET_PATCHSIZE: tuple[tuple[int, int], ...] = ((108, 60), (36, 20), (18, 10), (9, 5))
DET_INPUT_SIZE: tuple[int, int] = (432, 240)  # (width, height)


class _Deconv(nn.Module):
    def __init__(self, in_ch: int, out_ch: int, kernel_size: int = 3, padding: int = 0) -> None:
        super().__init__()
        self.conv = nn.Conv2d(in_ch, out_ch, kernel_size=kernel_size, stride=1, padding=padding)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = F.interpolate(x, scale_factor=2, mode="bilinear", align_corners=True)
        return self.conv(x)


class _Attention(nn.Module):
    """Scaled dot-product attention over the joint space-time token axis."""

    def forward(self, query: torch.Tensor, key: torch.Tensor, value: torch.Tensor) -> torch.Tensor:
        scores = torch.matmul(query, key.transpose(-2, -1)) / math.sqrt(query.size(-1))
        attn = F.softmax(scores, dim=-1)
        return torch.matmul(attn, value)


class MultiHeadedAttention(nn.Module):
    def __init__(self, patchsize: tuple[tuple[int, int], ...], d_model: int) -> None:
        super().__init__()
        self.patchsize = patchsize
        self.query_embedding = nn.Conv2d(d_model, d_model, kernel_size=1, padding=0)
        self.value_embedding = nn.Conv2d(d_model, d_model, kernel_size=1, padding=0)
        self.key_embedding = nn.Conv2d(d_model, d_model, kernel_size=1, padding=0)
        self.output_linear = nn.Sequential(
            nn.Conv2d(d_model, d_model, kernel_size=3, padding=1),
            nn.LeakyReLU(0.2, inplace=True),
        )
        self.attention = _Attention()

    def forward(self, x: torch.Tensor, b: int, c: int) -> torch.Tensor:
        bt, _, h, w = x.size()
        t = bt // b
        d_k = c // len(self.patchsize)
        query = self.query_embedding(x)
        key = self.key_embedding(x)
        value = self.value_embedding(x)
        output = []
        for (width, height), q, k, v in zip(
            self.patchsize,
            torch.chunk(query, len(self.patchsize), dim=1),
            torch.chunk(key, len(self.patchsize), dim=1),
            torch.chunk(value, len(self.patchsize), dim=1),
        ):
            out_w, out_h = w // width, h // height
            q = self._to_tokens(q, b, t, d_k, out_h, height, out_w, width)
            k = self._to_tokens(k, b, t, d_k, out_h, height, out_w, width)
            v = self._to_tokens(v, b, t, d_k, out_h, height, out_w, width)
            y = self.attention(q, k, v)
            y = y.view(b, t, out_h, out_w, d_k, height, width)
            y = y.permute(0, 1, 4, 2, 5, 3, 6).contiguous().view(bt, d_k, h, w)
            output.append(y)
        return self.output_linear(torch.cat(output, 1))

    @staticmethod
    def _to_tokens(
        feat: torch.Tensor, b: int, t: int, d_k: int, out_h: int, height: int, out_w: int, width: int
    ) -> torch.Tensor:
        feat = feat.view(b, t, d_k, out_h, height, out_w, width)
        return feat.permute(0, 1, 3, 5, 2, 4, 6).contiguous().view(b, t * out_h * out_w, d_k * height * width)


class FeedForward(nn.Module):
    def __init__(self, d_model: int) -> None:
        super().__init__()
        self.conv = nn.Sequential(
            nn.Conv2d(d_model, d_model, kernel_size=3, padding=2, dilation=2),
            nn.LeakyReLU(0.2, inplace=True),
            nn.Conv2d(d_model, d_model, kernel_size=3, padding=1),
            nn.LeakyReLU(0.2, inplace=True),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.conv(x)


class TransformerBlock(nn.Module):
    def __init__(self, patchsize: tuple[tuple[int, int], ...], hidden: int) -> None:
        super().__init__()
        self.attention = MultiHeadedAttention(patchsize, d_model=hidden)
        self.feed_forward = FeedForward(hidden)

    def forward(self, payload: dict) -> dict:
        x, b, c = payload["x"], payload["b"], payload["c"]
        x = x + self.attention(x, b, c)
        x = x + self.feed_forward(x)
        return {"x": x, "b": b, "c": c}


class InpaintGenerator(nn.Module):
    def __init__(
        self,
        *,
        channel: int = 256,
        stack_num: int = 8,
        patchsize: tuple[tuple[int, int], ...] = DET_PATCHSIZE,
    ) -> None:
        super().__init__()
        self.transformer = nn.Sequential(*[TransformerBlock(patchsize, hidden=channel) for _ in range(stack_num)])
        self.encoder = nn.Sequential(
            nn.Conv2d(3, 64, kernel_size=3, stride=2, padding=1),
            nn.LeakyReLU(0.2, inplace=True),
            nn.Conv2d(64, 64, kernel_size=3, stride=1, padding=1),
            nn.LeakyReLU(0.2, inplace=True),
            nn.Conv2d(64, 128, kernel_size=3, stride=2, padding=1),
            nn.LeakyReLU(0.2, inplace=True),
            nn.Conv2d(128, channel, kernel_size=3, stride=1, padding=1),
            nn.LeakyReLU(0.2, inplace=True),
        )
        self.decoder = nn.Sequential(
            _Deconv(channel, 128, kernel_size=3, padding=1),
            nn.LeakyReLU(0.2, inplace=True),
            nn.Conv2d(128, 64, kernel_size=3, stride=1, padding=1),
            nn.LeakyReLU(0.2, inplace=True),
            _Deconv(64, 64, kernel_size=3, padding=1),
            nn.LeakyReLU(0.2, inplace=True),
            nn.Conv2d(64, 3, kernel_size=3, stride=1, padding=1),
        )

    def infer(self, feat: torch.Tensor) -> torch.Tensor:
        """Run the spatial-temporal transformer over encoder features ``[t, c, h, w]``."""
        _, c, _, _ = feat.size()
        return self.transformer({"x": feat, "b": 1, "c": c})["x"]


__all__ = ["InpaintGenerator", "DET_PATCHSIZE", "DET_INPUT_SIZE"]
