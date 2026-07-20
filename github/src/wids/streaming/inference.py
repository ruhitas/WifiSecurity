"""Inference service: feature-vectors -> detections.

Phase 5 uses a transparent rule-based scorer so the pipeline produces real,
explainable verdicts end to end. Phases 9-10 replace :meth:`score` with the
hybrid CNN+Transformer+GNN+Autoencoder ensemble behind the same interface.
"""
from __future__ import annotations

import json
import time
import uuid

from kafka import KafkaConsumer

from ..config import settings
from ..connections import get_kafka_producer

FEATURE_TOPIC = "wids.feature-vectors"
DETECTION_TOPIC = "wids.detections"


def score(fv: dict) -> dict:
    """Return a verdict dict for a feature vector (rule-based stub)."""
    deauth_rate = fv.get("deauth_rate", 0.0)
    deauth_count = fv.get("deauth_count", 0)
    disassoc = fv.get("disassoc_count", 0)
    retry_rate = fv.get("retry_rate", 0.0)

    if deauth_count >= 8 and deauth_rate >= 0.4:
        return {
            "label": "deauth_flood",
            "score": round(min(0.99, 0.5 + deauth_rate / 2), 4),
            "confidence": 0.92,
            "severity": "high",
            "top_features": ["deauth_rate", "deauth_count"],
            "explanation": (
                f"Deauthentication flood: {deauth_count} deauth frames "
                f"({deauth_rate:.0%} of the window) from sensor {fv.get('sensor_id')}."
            ),
        }
    if disassoc >= 8:
        return {"label": "disassoc_flood", "score": 0.8, "confidence": 0.8,
                "severity": "high", "top_features": ["disassoc_count"],
                "explanation": f"Disassociation flood: {disassoc} frames."}
    if retry_rate >= 0.5:
        return {"label": "possible_interference", "score": 0.55, "confidence": 0.5,
                "severity": "low", "top_features": ["retry_rate"],
                "explanation": f"High retry rate ({retry_rate:.0%}) may indicate interference."}
    return {"label": "normal", "score": round(deauth_rate, 4), "confidence": 0.6,
            "severity": "info", "top_features": [], "explanation": "No attack pattern in window."}


class InferenceService:
    def __init__(self, emit_normal: bool = False):
        self.emit_normal = emit_normal
        self._producer = get_kafka_producer()

    def run(self, stop_event=None, group_id="wids-inference", offset="latest"):
        consumer = KafkaConsumer(
            FEATURE_TOPIC,
            bootstrap_servers=settings.kafka_bootstrap,
            group_id=group_id,
            auto_offset_reset=offset,
            enable_auto_commit=True,
            value_deserializer=lambda b: json.loads(b.decode("utf-8")),
        )
        produced = 0
        try:
            while stop_event is None or not stop_event.is_set():
                batch = consumer.poll(timeout_ms=1000, max_records=500)
                for _tp, records in batch.items():
                    for rec in records:
                        fv = rec.value
                        verdict = score(fv)
                        if verdict["label"] == "normal" and not self.emit_normal:
                            continue
                        detection = {
                            "event_id": str(uuid.uuid4()),
                            "sensor_id": fv.get("sensor_id"),
                            "window_ts": fv.get("window_ts"),
                            "frame_count": fv.get("frame_count"),
                            "created_at": time.time(),
                            **verdict,
                        }
                        self._producer.send(DETECTION_TOPIC,
                                            key=str(fv.get("sensor_id")).encode("utf-8"),
                                            value=detection)
                        produced += 1
        finally:
            self._producer.flush()
            consumer.close()
        return produced
