"""Real-time streaming pipeline (Phase 5).

raw-frames --> [FeatureExtractorService] --> feature-vectors
           --> [InferenceService]        --> detections
           --> [DetectionSink]           --> MSSQL + Elasticsearch

Phase 5 wires the stages with a minimal (~14) feature set and a rule-based
inference stub. Phase 6 expands to 300+ features; Phases 9-10 replace the stub
with the hybrid CNN+Transformer+GNN+AE ensemble.
"""
from .feature_extractor import FeatureExtractorService
from .inference import InferenceService
from .sink import DetectionSink

__all__ = ["FeatureExtractorService", "InferenceService", "DetectionSink"]
