"""Policy engine: decide the response mode and action set for a detection."""
from __future__ import annotations


class PolicyEngine:
    def __init__(self, auto_conf: float = 0.85, alert_conf: float = 0.6):
        self.auto_conf = auto_conf
        self.alert_conf = alert_conf

    def evaluate(self, det: dict) -> dict:
        label = det.get("label")
        conf = float(det.get("confidence", 0.0))
        sev = det.get("severity", "info")

        if label in (None, "normal") or sev == "info":
            return {"mode": "ignore", "actions": [], "reason": "benign / informational"}

        if sev in ("high", "critical") and conf >= self.auto_conf:
            return {"mode": "auto",
                    "actions": ["mac_block", "vlan_quarantine", "siem_forward", "notify"],
                    "reason": f"{sev} severity, confidence {conf:.2f} >= {self.auto_conf} -> auto-mitigate"}

        if conf >= self.alert_conf:
            return {"mode": "alert", "actions": ["siem_forward", "notify"],
                    "reason": f"confidence {conf:.2f} below auto threshold -> alert only"}

        return {"mode": "alert", "actions": ["notify"],
                "reason": "low confidence -> notify only"}
