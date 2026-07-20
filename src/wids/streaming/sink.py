"""Detection sink: detections -> MSSQL + Elasticsearch (+ alert log).

Persists every detection to the MSSQL detection_events table (source of truth)
and indexes it into the shared Elasticsearch node under the wids- prefix
(replicas=0 to stay green on the single node). Elasticsearch failures are
non-fatal (e.g. read-only from a full disk).
"""
from __future__ import annotations

import json

from kafka import KafkaConsumer

from ..config import settings
from ..connections import get_mssql, get_es

DETECTION_TOPIC = "wids.detections"


class DetectionSink:
    def __init__(self, index_es: bool = True, print_alerts: bool = True):
        self.index_es = index_es
        self.print_alerts = print_alerts
        self._conn = get_mssql()
        self._conn.autocommit = True
        self._es = None
        self._es_index = settings.es_index("detections")
        if index_es:
            self._init_es()

    def _init_es(self):
        try:
            self._es = get_es()
            if not self._es.indices.exists(index=self._es_index):
                self._es.indices.create(
                    index=self._es_index,
                    settings={"number_of_replicas": 0},
                )
        except Exception as e:
            print(f"[sink] Elasticsearch unavailable, continuing without it: {str(e)[:100]}")
            self._es = None

    def _persist_sql(self, d: dict):
        cur = self._conn.cursor()
        cur.execute(
            """INSERT INTO detection_events
               (event_id, sensor_id, attack_type, score, confidence, window_ts, frame_count, explanation)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            d.get("event_id"), d.get("sensor_id"), d.get("label"), d.get("score"),
            d.get("confidence"), d.get("window_ts"), d.get("frame_count"),
            (d.get("explanation") or "")[:512],
        )

    def _index_es(self, d: dict):
        if self._es is None:
            return
        try:
            self._es.index(index=self._es_index, id=d.get("event_id"), document=d)
        except Exception as e:
            print(f"[sink] ES index failed: {str(e)[:100]}")

    def run(self, stop_event=None, group_id="wids-sink", offset="latest"):
        consumer = KafkaConsumer(
            DETECTION_TOPIC,
            bootstrap_servers=settings.kafka_bootstrap,
            group_id=group_id,
            auto_offset_reset=offset,
            enable_auto_commit=True,
            value_deserializer=lambda b: json.loads(b.decode("utf-8")),
        )
        stored = 0
        try:
            while stop_event is None or not stop_event.is_set():
                batch = consumer.poll(timeout_ms=1000, max_records=200)
                for _tp, records in batch.items():
                    for rec in records:
                        d = rec.value
                        try:
                            self._persist_sql(d)
                        except Exception as e:
                            print(f"[sink] SQL insert failed: {str(e)[:100]}")
                            continue
                        self._index_es(d)
                        stored += 1
                        if self.print_alerts and d.get("severity") in ("high", "medium"):
                            print(f"[ALERT] {d.get('severity','?').upper():<6} "
                                  f"{d.get('label')} · sensor={d.get('sensor_id')} "
                                  f"· conf={d.get('confidence')} · {d.get('explanation')}")
        finally:
            consumer.close()
            try:
                self._conn.close()
            except Exception:
                pass
        return stored
