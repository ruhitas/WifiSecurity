"""Unified dataset builder (Phase 7).

Assembles a labeled feature dataset from multiple sources — synthetic normal
traffic, generated multi-class attacks, and replayed capture files (e.g. AWID3,
Phase 4 PcapReplaySource) — using the Phase 6 feature extractor. Output is a CSV
plus a JSON manifest that Phase 8 (feature selection) and Phases 9-10 (model
training) consume.
"""
from .builder import DatasetBuilder, DEFAULT_CLASSES

__all__ = ["DatasetBuilder", "DEFAULT_CLASSES"]
