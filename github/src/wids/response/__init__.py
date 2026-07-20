"""Autonomous response (Phase 13).

Policy-gated, auditable mitigation. Detections are evaluated by a PolicyEngine
(confidence/severity gating); authorized actions run through pluggable executors
(MAC block, disable AP, firewall rule, VLAN quarantine, webhook, SIEM forward,
RabbitMQ notification). Enforcement actions are dry-run by default (no live
WLC/firewall configured); notifications via the existing RabbitMQ are real.
Every action is persisted (MSSQL response_actions) and can be overridden.
"""
from .engine import ResponseEngine
from .policy import PolicyEngine

__all__ = ["ResponseEngine", "PolicyEngine"]
