"""Unsupervised unseen-attack / unknown-attack detection (Phase 11).

Detectors are trained on NORMAL traffic only and score any deviation as an
anomaly, so they flag attacks never seen during training. Provides Isolation
Forest and One-Class SVM (classical) plus AutoEncoder, VAE and Deep SVDD (deep).
All share a fit(X_normal) / score(X)->anomaly-score(higher=worse) interface.
"""
from .detectors import (AutoEncoderAD, DeepSVDD, IsolationForestAD,
                        OneClassSVMAD, VAE_AD, build_detectors)

__all__ = ["IsolationForestAD", "OneClassSVMAD", "AutoEncoderAD", "VAE_AD",
           "DeepSVDD", "build_detectors"]
