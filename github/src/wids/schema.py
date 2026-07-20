"""Relational schema (MSSQL / WirelesSecureDB) for the sensor fabric.

Phase 3 introduces the sensor registry and capture-session tables from the
SAD ER model (section 8.2). Later phases add detection/event tables.
"""
from __future__ import annotations

from .connections import get_mssql

DDL = [
    # --- sensors ------------------------------------------------------------
    """
    IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'sensors')
    CREATE TABLE sensors (
        sensor_id    NVARCHAR(64)  NOT NULL PRIMARY KEY,
        name         NVARCHAR(128) NULL,
        location     NVARCHAR(128) NULL,
        nic_chipset  NVARCHAR(128) NULL,
        status       NVARCHAR(32)  NULL,
        created_at   DATETIME2     NOT NULL DEFAULT SYSUTCDATETIME(),
        last_seen    DATETIME2     NULL
    );
    """,
    # --- capture_sessions ---------------------------------------------------
    """
    IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'capture_sessions')
    CREATE TABLE capture_sessions (
        session_id   NVARCHAR(64) NOT NULL PRIMARY KEY,
        sensor_id    NVARCHAR(64) NOT NULL,
        channel      INT          NULL,
        source       NVARCHAR(32) NULL,
        started_at   DATETIME2    NOT NULL DEFAULT SYSUTCDATETIME(),
        ended_at     DATETIME2    NULL
    );
    """,
    # --- detection_events (Phase 5) ----------------------------------------
    """
    IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'detection_events')
    CREATE TABLE detection_events (
        event_id     NVARCHAR(64)  NOT NULL PRIMARY KEY,
        sensor_id    NVARCHAR(64)  NULL,
        attack_type  NVARCHAR(64)  NULL,
        score        FLOAT         NULL,
        confidence   FLOAT         NULL,
        window_ts    FLOAT         NULL,
        frame_count  INT           NULL,
        explanation  NVARCHAR(512) NULL,
        created_at   DATETIME2     NOT NULL DEFAULT SYSUTCDATETIME()
    );
    """,
    # --- response_actions (Phase 13) ---------------------------------------
    """
    IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'response_actions')
    CREATE TABLE response_actions (
        action_id    NVARCHAR(64)  NOT NULL PRIMARY KEY,
        event_id     NVARCHAR(64)  NULL,
        sensor_id    NVARCHAR(64)  NULL,
        type         NVARCHAR(48)  NULL,
        target       NVARCHAR(64)  NULL,
        status       NVARCHAR(32)  NULL,
        actor        NVARCHAR(64)  NULL,
        dry_run      BIT           NULL,
        detail       NVARCHAR(512) NULL,
        created_at   DATETIME2     NOT NULL DEFAULT SYSUTCDATETIME()
    );
    """,
]

_TABLES = ("sensors", "capture_sessions", "detection_events", "response_actions")


def ensure_schema() -> list[str]:
    """Create the Phase 3 tables if they do not exist. Returns table names."""
    conn = get_mssql()
    conn.autocommit = True
    cur = conn.cursor()
    for stmt in DDL:
        cur.execute(stmt)
    placeholders = ",".join("?" for _ in _TABLES)
    cur.execute(f"SELECT name FROM sys.tables WHERE name IN ({placeholders}) ORDER BY name", *_TABLES)
    tables = [r[0] for r in cur.fetchall()]
    conn.close()
    return tables


if __name__ == "__main__":
    print("Ensured tables:", ", ".join(ensure_schema()))
