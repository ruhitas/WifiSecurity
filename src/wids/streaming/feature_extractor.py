"""Feature-extraction service: raw-frames -> feature-vectors.

Maintains a per-sensor tumbling window; when the window fills (or on idle), it
computes a feature vector, publishes it to the feature-vectors topic, and caches
the latest vector per sensor in the Redis feature store (SAD ADR-006).
"""
from __future__ import annotations

import json
import time
from collections import defaultdict

from kafka import KafkaConsumer

from ..config import settings
from ..connections import get_kafka_producer, get_redis
from .features import compute_features

RAW_TOPIC = "wids.raw-frames"
FEATURE_TOPIC = "wids.feature-vectors"
WINDOW_FRAMES = 40          # tumbling window size
IDLE_FLUSH_MIN = 5          # flush partial windows after idle if >= this many


class FeatureExtractorService:
    def __init__(self, window_frames: int = WINDOW_FRAMES):
        self.window_frames = window_frames
        self._buffers = defaultdict(list)
        self._producer = get_kafka_producer()
        self._redis = get_redis()

    def _emit(self, sensor_id: str, frames: list[dict]) -> dict:
        feats = compute_features(frames)
        msg = {
            "sensor_id": sensor_id,
            "window_ts": time.time(),
            "session_id": frames[-1].get("session_id"),
            **feats,
        }
        self._producer.send(FEATURE_TOPIC, key=sensor_id.encode("utf-8"), value=msg)
        # cache latest vector in the Redis feature store
        try:
            self._redis.setex(f"wids:fv:{sensor_id}:latest", 60, json.dumps(msg))
        except Exception:
            pass
        return msg

    def run(self, stop_event=None, group_id="wids-feature-extractor",
            offset="latest", idle_flush=True):
        consumer = KafkaConsumer(
            RAW_TOPIC,
            bootstrap_servers=settings.kafka_bootstrap,
            group_id=group_id,
            auto_offset_reset=offset,
            enable_auto_commit=True,
            value_deserializer=lambda b: json.loads(b.decode("utf-8")),
        )
        emitted = 0
        empty_polls = 0
        try:
            while stop_event is None or not stop_event.is_set():
                batch = consumer.poll(timeout_ms=1000, max_records=1000)
                if not batch:
                    empty_polls += 1
                    if idle_flush and empty_polls >= 2:
                        for sid, buf in list(self._buffers.items()):
                            if len(buf) >= IDLE_FLUSH_MIN:
                                self._emit(sid, buf)
                                emitted += 1
                                self._buffers[sid] = []
                        empty_polls = 0
                    continue
                empty_polls = 0
                for _tp, records in batch.items():
                    for rec in records:
                        f = rec.value
                        sid = f.get("sensor_id", "?")
                        buf = self._buffers[sid]
                        buf.append(f)
                        if len(buf) >= self.window_frames:
                            self._emit(sid, buf)
                            emitted += 1
                            self._buffers[sid] = []
        finally:
            self._producer.flush()
            consumer.close()
        return emitted
