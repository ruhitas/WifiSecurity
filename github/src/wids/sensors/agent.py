"""SensorAgent — one wireless sensor node.

Registers with the central registry, opens a capture session, and streams
frames (tagged with its sensor_id and session_id) to the Kafka raw-frames
topic, emitting periodic heartbeats. The frame source is pluggable: synthetic
now (Phase 3), real 802.11 capture in Phase 4.
"""
from __future__ import annotations

import time

from ..connections import get_kafka_producer
from ..config import settings
from .frames import FrameSource, SyntheticFrameSource
from .registry import SensorRegistry

RAW_TOPIC = "wids.raw-frames"


class SensorAgent:
    def __init__(self, sensor_id, name=None, location=None,
                 nic_chipset="synthetic", channel=6):
        self.sensor_id = sensor_id
        self.name = name or sensor_id
        self.location = location
        self.nic_chipset = nic_chipset
        self.channel = channel

    def run(self, source: FrameSource | None = None, max_frames=None,
            rate_hz=50, heartbeat_every=2.0, verbose=False) -> int:
        """Stream frames until max_frames is reached (or forever if None)."""
        source = source or SyntheticFrameSource(channel=self.channel)
        registry = SensorRegistry()
        producer = get_kafka_producer()
        registry.register_sensor(self.sensor_id, self.name, self.location,
                                 self.nic_chipset, status="online")
        session_id = registry.start_session(self.sensor_id, self.channel, source.source_name)
        registry.heartbeat(self.sensor_id)

        interval = 1.0 / rate_hz if rate_hz else 0
        last_hb = time.time()
        count = 0
        try:
            for frame in source.iterate():
                frame["sensor_id"] = self.sensor_id
                frame["session_id"] = session_id
                producer.send(RAW_TOPIC, key=self.sensor_id.encode("utf-8"), value=frame)
                count += 1
                now = time.time()
                if now - last_hb >= heartbeat_every:
                    registry.heartbeat(self.sensor_id)
                    last_hb = now
                if max_frames and count >= max_frames:
                    break
                if interval:
                    time.sleep(interval)
        finally:
            producer.flush()
            producer.close()
            registry.end_session(session_id)
            registry.set_status(self.sensor_id, "offline")
            registry.close()
        if verbose:
            print(f"[{self.sensor_id}] sent {count} frames to {RAW_TOPIC} "
                  f"(bootstrap={settings.kafka_bootstrap})")
        return count
