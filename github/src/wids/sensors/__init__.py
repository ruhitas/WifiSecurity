"""Distributed wireless sensor fabric (Phase 3).

Each sensor captures 802.11 traffic (Phase 4) and streams it, tagged with its
sensor_id, to the central platform over Kafka. A registry tracks sensor identity
and liveness so the central AI server can correlate across sensors (Phase 7).
"""
from .agent import SensorAgent
from .registry import SensorRegistry

__all__ = ["SensorAgent", "SensorRegistry"]
