"""Explainable AI (Phase 12).

Turns a detection into an operator-facing reasoning report: the features that
most pushed the model toward its verdict (SHAP contributions), the confidence,
and a plain-language explanation. Complements the model-native attention/saliency
from Phase 10. Addresses the explainability gap the literature review found for
802.11 IDS.
"""
from .explainer import Explainer

__all__ = ["Explainer"]
