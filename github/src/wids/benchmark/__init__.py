"""Automated model benchmark (Phase 9).

Trains and evaluates a suite of classical + boosting classifiers on the Phase 7
dataset with stratified cross-validation, reporting accuracy / precision /
recall / F1 / ROC-AUC plus training time and per-sample inference latency, and
ranks them into a benchmark table. Deep models (CNN/Transformer/GNN, Phase 10)
plug into the same reporting.
"""
from .runner import build_models, benchmark, confusion_for_best, FAST_MODELS

__all__ = ["build_models", "benchmark", "confusion_for_best", "FAST_MODELS"]
