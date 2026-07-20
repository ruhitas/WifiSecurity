"""Feature engineering / selection (Phase 8).

Runs several complementary feature-selection methods on the Phase 7 dataset,
compares their rankings, and produces a consensus ranking + a selected feature
subset for Phase 9 (benchmark) and Phase 10 (hybrid model).
"""
from .selectors import load_dataset, run_all_methods, consensus_ranking

__all__ = ["load_dataset", "run_all_methods", "consensus_ranking"]
