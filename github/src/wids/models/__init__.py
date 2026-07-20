"""Hybrid deep-learning models (Phase 10).

HybridNet fuses a 1D-CNN branch (local feature patterns) with a Transformer
self-attention branch (feature interactions) over the Phase 6 feature vector,
with gradient-based XAI and attention read-out. A from-scratch GNN (gnn.py)
models the station<->BSSID graph — the relational novelty from the SAD/lit-review.
"""
from .hybrid import HybridNet

__all__ = ["HybridNet"]
