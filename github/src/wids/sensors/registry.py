"""Sensor registry and liveness tracking.

Identity/config is persisted in MSSQL (sensors, capture_sessions); fast liveness
uses a Redis heartbeat key with a TTL. One SensorRegistry instance owns one MSSQL
connection, so create a separate instance per thread/process.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from ..connections import get_mssql, get_redis

HB_KEY = "wids:sensor:{sid}:hb"


class SensorRegistry:
    def __init__(self):
        self._conn = get_mssql()
        self._conn.autocommit = True
        self._r = get_redis()

    # -- identity ----------------------------------------------------------
    def register_sensor(self, sensor_id, name=None, location=None,
                        nic_chipset=None, status="online"):
        cur = self._conn.cursor()
        cur.execute(
            """
            MERGE sensors AS t
            USING (SELECT ? AS sensor_id) AS s ON t.sensor_id = s.sensor_id
            WHEN MATCHED THEN UPDATE SET
                name = ?, location = ?, nic_chipset = ?, status = ?, last_seen = SYSUTCDATETIME()
            WHEN NOT MATCHED THEN
                INSERT (sensor_id, name, location, nic_chipset, status, last_seen)
                VALUES (?, ?, ?, ?, ?, SYSUTCDATETIME());
            """,
            sensor_id, name, location, nic_chipset, status,
            sensor_id, name, location, nic_chipset, status,
        )

    def set_status(self, sensor_id, status):
        cur = self._conn.cursor()
        cur.execute("UPDATE sensors SET status = ?, last_seen = SYSUTCDATETIME() WHERE sensor_id = ?",
                    status, sensor_id)
        if status == "offline":
            # drop the liveness key so the sensor immediately reads as offline
            self._r.delete(HB_KEY.format(sid=sensor_id))

    # -- sessions ----------------------------------------------------------
    def start_session(self, sensor_id, channel=None, source=None) -> str:
        session_id = str(uuid.uuid4())
        cur = self._conn.cursor()
        cur.execute(
            "INSERT INTO capture_sessions (session_id, sensor_id, channel, source) VALUES (?, ?, ?, ?)",
            session_id, sensor_id, channel, source,
        )
        return session_id

    def end_session(self, session_id):
        cur = self._conn.cursor()
        cur.execute("UPDATE capture_sessions SET ended_at = SYSUTCDATETIME() WHERE session_id = ?",
                    session_id)

    # -- liveness ----------------------------------------------------------
    def heartbeat(self, sensor_id, ttl=15):
        self._r.setex(HB_KEY.format(sid=sensor_id), ttl,
                      datetime.now(timezone.utc).isoformat())
        cur = self._conn.cursor()
        cur.execute("UPDATE sensors SET last_seen = SYSUTCDATETIME() WHERE sensor_id = ?", sensor_id)

    def list_status(self):
        cur = self._conn.cursor()
        cur.execute("SELECT sensor_id, name, location, status, last_seen FROM sensors ORDER BY sensor_id")
        rows = []
        for sid, name, location, status, last_seen in cur.fetchall():
            online = self._r.exists(HB_KEY.format(sid=sid)) == 1
            rows.append({
                "sensor_id": sid, "name": name, "location": location,
                "status": status, "last_seen": last_seen,
                "online": online,
            })
        return rows

    def close(self):
        try:
            self._conn.close()
        except Exception:
            pass
