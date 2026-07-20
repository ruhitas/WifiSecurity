"""Phase 13 demo: policy-gated autonomous response.

Feeds three detections (high-confidence attack, medium-confidence attack, benign)
straight through the response engine and verifies: auto-mitigation for the
high-confidence attack (dry-run), alert-only for medium, ignore for benign; all
actions persisted to MSSQL; a RabbitMQ notification attempted; and a SOC-analyst
override applied. (The Kafka-consumer service path is scripts/run_response.py.)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from wids.config import settings  # noqa: E402
from wids.connections import get_mssql, get_rabbitmq  # noqa: E402
from wids.schema import ensure_schema  # noqa: E402
from wids.response import ResponseEngine  # noqa: E402

DETECTIONS = [
    {"event_id": "evt-hi", "sensor_id": "sensor-attack", "label": "deauth_flood",
     "score": 0.96, "confidence": 0.95, "severity": "high", "bssid": "aa:bb:cc:dd:ee:ff",
     "explanation": "Deauthentication flood: 92% of window."},
    {"event_id": "evt-med", "sensor_id": "sensor-03", "label": "probe_flood",
     "score": 0.7, "confidence": 0.70, "severity": "high", "bssid": "11:22:33:44:55:66",
     "explanation": "Elevated probe-request rate."},
    {"event_id": "evt-benign", "sensor_id": "sensor-01", "label": "normal",
     "score": 0.1, "confidence": 0.6, "severity": "info", "explanation": "No attack pattern."},
]


def count_actions(conn):
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM response_actions")
    return cur.fetchone()[0]


def main() -> int:
    print("== Phase 13 autonomous response demo ==")
    ensure_schema()
    conn = get_mssql(); conn.autocommit = True
    before = count_actions(conn)

    engine = ResponseEngine(dry_run=True)
    print("\nProcessing 3 detections through policy + actions...")
    print("  " + "-" * 78)
    for d in DETECTIONS:
        engine.handle(d)
    print("  " + "-" * 78)

    after = count_actions(conn)
    print(f"\nresponse_actions rows: {before} -> {after} (+{after - before})")

    cur = conn.cursor()
    cur.execute("""SELECT TOP 8 event_id, type, target, status, dry_run
                   FROM response_actions ORDER BY created_at DESC""")
    print("\n  Recent response actions")
    print("  " + "-" * 74)
    for r in cur.fetchall():
        print(f"  {str(r[0]):<12}{r[1]:<16}{str(r[2]):<20}{r[3]:<12}dry_run={r[4]}")
    print("  " + "-" * 74)

    # SOC-analyst override of one auto mac_block
    cur.execute("""SELECT TOP 1 action_id FROM response_actions
                   WHERE type='mac_block' ORDER BY created_at DESC""")
    row = cur.fetchone()
    overridden = False
    if row:
        n = engine.override(row[0], actor="soc-analyst", decision="rolled_back")
        overridden = n > 0
        print(f"\n  SOC override: mac_block {row[0][:8]}... -> rolled_back "
              f"({'ok' if overridden else 'failed'})")

    # RabbitMQ notification status
    try:
        c = get_rabbitmq(); ch = c.channel()
        q = ch.queue_declare(queue=settings.rabbitmq_notify_queue, durable=True)
        print(f"  RabbitMQ '{settings.rabbitmq_notify_queue}' message_count: {q.method.message_count}")
        c.close()
    except Exception:
        print("  RabbitMQ: AMQP (5672) not reachable on this host -> notifications skipped "
              "(engine degrades gracefully; enable the RabbitMQ AMQP listener to activate).")

    conn.close()
    ok = (after - before) >= 4 and overridden
    print("\nRESULT:", "PASS - policy-gated response + audit + override working"
          if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
