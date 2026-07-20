"""HybridNet: CNN + Transformer(attention) fusion for tabular 802.11 features."""
from __future__ import annotations

import torch
import torch.nn as nn


class AttnBlock(nn.Module):
    """One multi-head self-attention block that stashes its attention weights."""

    def __init__(self, d_model: int, nhead: int):
        super().__init__()
        self.attn = nn.MultiheadAttention(d_model, nhead, batch_first=True)
        self.norm1 = nn.LayerNorm(d_model)
        self.ff = nn.Sequential(nn.Linear(d_model, d_model * 2), nn.ReLU(),
                                nn.Linear(d_model * 2, d_model))
        self.norm2 = nn.LayerNorm(d_model)
        self.last_attn = None

    def forward(self, x):
        need = not self.training
        a, w = self.attn(x, x, x, need_weights=need, average_attn_weights=True)
        if need:
            self.last_attn = w.detach()   # (B, D, D)
        x = self.norm1(x + a)
        x = self.norm2(x + self.ff(x))
        return x


class HybridNet(nn.Module):
    def __init__(self, n_features: int, n_classes: int, d_model: int = 32, nhead: int = 4):
        super().__init__()
        self.n_features = n_features
        # CNN branch over the feature vector as a 1D signal
        self.cnn = nn.Sequential(
            nn.Conv1d(1, 32, kernel_size=5, padding=2), nn.ReLU(),
            nn.Conv1d(32, 64, kernel_size=3, padding=1), nn.ReLU(),
            nn.AdaptiveMaxPool1d(1),
        )
        # Transformer branch: each feature becomes a token (scalar -> d_model)
        self.feat_embed = nn.Linear(1, d_model)
        self.pos = nn.Parameter(torch.randn(1, n_features, d_model) * 0.02)
        self.block = AttnBlock(d_model, nhead)
        # fusion head
        self.head = nn.Sequential(
            nn.Linear(64 + d_model, 64), nn.ReLU(), nn.Dropout(0.2),
            nn.Linear(64, n_classes),
        )

    def forward(self, x):  # x: (B, D)
        c = self.cnn(x.unsqueeze(1)).squeeze(-1)             # (B, 64)
        t = self.feat_embed(x.unsqueeze(-1)) + self.pos      # (B, D, d_model)
        t = self.block(t).mean(dim=1)                        # (B, d_model)
        return self.head(torch.cat([c, t], dim=1))

    def feature_attention(self):
        """Per-feature attention importance (mean over batch & queries)."""
        if self.block.last_attn is None:
            return None
        return self.block.last_attn.mean(dim=(0, 1))         # (D,)
