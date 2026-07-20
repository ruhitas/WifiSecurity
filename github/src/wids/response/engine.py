"""Response engine: consume detections, gate by policy, execute + audit actions."""
from __future__ import annotations

import json

from kafka import KafkaConsumer

from ..config import settings
from ..connections import get_kafka_producer, get_mssql, get_rabbitmq
from .actions import REGISTRY
from .policy import PolicyEngine

DETECTION_TOPIC = "wids.detections"


class ResponseEngine:
    def __init__(self, dry_run: bool = True):
        self.dry_run = dry_run
        self.policy = PolicyEngine()
        self._kafka = get_kafka_producer()
        self._conn = get_mssql(); self._conn.autocommit = True
        self._rmq = None
        self._rmq_ch = None
        self._init_rmq()

    def _init_rmq(self):
        try:
            self._rmq = get_rabbitmq()
            self._rmq_ch = self._rmq.channel()
            self._rmq_ch.queue_declare(queue=settings.rabbitmq_notify_queue, durable=True)
        except Exception as e:
            print(f"[response] RabbitMQ unavailable, notifications disabled: {str(e)[:100]}")
            self._rmq_ch = None

    def _ctx(self):
        return {"kafka": self._kafka, "rmq_channel": self._rmq_ch,
                "notify_queue": settings.rabbitmq_notify_queue}

    def _record(self, det, res, actor="auto"):
        cur = self._conn.cursor()
        cur.execute(
            """INSERT INTO response_actions
               (action_id, event_id, sensor_id, type, target, status, actor, dry_run, detail)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            res["action_id"], det.get("event_id"), det.get("sensor_id"), res["type"],
            res["target"], res["status"], actor, 1 if self.dry_run else 0,
            (res.get("detail") or "")[:512])
        self._kafka.send("wids.responses", value={**res, "event_id": det.get("event_id")})

    def handle(self, det: dict) -> list[dict]:
        decision = self.policy.evaluate(det)
        if decision["mode"] == "ignore":
            return []
        ctx = self._ctx()
        out = []
        for atype in decision["actions"]:
            action = REGISTRY.get(atype)
            if not action:
                continue
            res = action.execute(det, self.dry_run, ctx)
            self._record(det, res)
            out.append(res)
        print(f"[RESPONSE] {decision['mode'].upper():<6} {det.get('label')} "
              f"sensor={det.get('sensor_id')} conf={det.get('confidence')} -> "
              + ", ".join(f"{r['type']}:{r['status']}" for r in out))
        return out

    def override(self, action_id, actor, decision="rolled_back"):
        cur = self._conn.cursor()
        cur.execute("UPDATE response_actions SET status = ?, actor = ? WHERE action_id = ?",
                    decision, actor, action_id)
        self._kafka.send("wids.audit", value={"kind": "override", "action_id": action_id,
                                              "actor": actor, "decision": decision})
        self._kafka.flush()
        return cur.rowcount

    def run(self, stop_event=None, group_id="wids-response", offset="latest"):
        consumer = KafkaConsumer(
            DETECTION_TOPIC, bootstrap_servers=settings.kafka_bootstrap,
            group_id=group_id, auto_offset_reset=offset, enable_auto_commit=True,
            value_deserializer=lambda b: json.loads(b.decode("utf-8")))
        handled = 0
        try:
            while stop_event is None or not stop_event.is_set():
                batch = consumer.poll(timeout_ms=1000, max_records=200)
                for _tp, records in batch.items():
                    for rec in records:
                        self.handle(rec.value)
                        handled += 1
        finally:
            self._kafka.flush()
            consumer.close()
        return handled
