"""Pluggable response-action executors.

Each action has execute(detection, dry_run, ctx) -> result dict. Enforcement
actions are dry-run by default (no live WLC/firewall endpoint configured);
SIEM-forward and RabbitMQ notify perform real local I/O.
"""
from __future__ import annotations

import json
import uuid


def _result(atype, target, status, detail):
    return {"action_id": str(uuid.uuid4()), "type": atype, "target": target,
            "status": status, "detail": detail}


def _target(det):
    return det.get("target") or det.get("bssid") or det.get("sensor_id") or "unknown"


class DryRunAction:
    """Enforcement action that is simulated unless a real endpoint is wired."""

    def __init__(self, atype):
        self.atype = atype

    def execute(self, det, dry_run, ctx):
        target = _target(det)
        if dry_run:
            return _result(self.atype, target, "simulated",
                           f"[dry-run] would {self.atype} target {target}")
        return _result(self.atype, target, "skipped",
                       f"no live {self.atype} endpoint configured")


class SiemForwardAction:
    atype = "siem_forward"

    def execute(self, det, dry_run, ctx):
        try:
            ctx["kafka"].send("wids.audit", value={"kind": "siem_event", **det})
            return _result(self.atype, det.get("sensor_id", "?"), "sent",
                           "forwarded to wids.audit (SIEM)")
        except Exception as e:
            return _result(self.atype, det.get("sensor_id", "?"), "failed", str(e)[:100])


class NotifyRabbitMQAction:
    atype = "notify"

    def execute(self, det, dry_run, ctx):
        ch = ctx.get("rmq_channel")
        target = det.get("sensor_id", "?")
        if ch is None:
            return _result(self.atype, target, "skipped", "RabbitMQ unavailable")
        try:
            msg = {"text": det.get("explanation") or det.get("label"),
                   "label": det.get("label"), "severity": det.get("severity"),
                   "sensor_id": det.get("sensor_id"), "confidence": det.get("confidence")}
            ch.basic_publish(exchange="", routing_key=ctx["notify_queue"],
                             body=json.dumps(msg))
            return _result(self.atype, target, "sent",
                           f"published to RabbitMQ '{ctx['notify_queue']}'")
        except Exception as e:
            return _result(self.atype, target, "failed", str(e)[:100])


REGISTRY = {
    "mac_block": DryRunAction("mac_block"),
    "disable_ap": DryRunAction("disable_ap"),
    "firewall_rule": DryRunAction("firewall_rule"),
    "vlan_quarantine": DryRunAction("vlan_quarantine"),
    "webhook": DryRunAction("webhook"),
    "siem_forward": SiemForwardAction(),
    "notify": NotifyRabbitMQAction(),
}
