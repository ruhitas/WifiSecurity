"""Phase 5 end-to-end streaming demo / verification.

Runs the full pipeline (feature extractor -> inference -> sink) in background
threads, injects a deauthentication flood from one sensor plus normal traffic
from another, and verifies a deauth_flood detection flows all the way through
and is persisted to MSSQL (and indexed to Elasticsearch when writable).
"""
import sys
import threading
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from wids.schema import ensure_schema  # noqa: E402
from wids.connections import get_mssql  # noqa: E402
from wids.sensors import SensorAgent  # noqa: E402
from wids.sensors.frames import SyntheticFrameSource  # noqa: E402
from wids.streaming import FeatureExtractorService, InferenceService, DetectionSink  # noqa: E402


def deauth_count(conn):
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM detection_events WHERE attack_type = 'deauth_flood'")
    return cur.fetchone()[0]


def main() -> int:
    print("== Phase 5 streaming pipeline demo ==")
    ensure_schema()
    conn = get_mssql(); conn.autocommit = True
    before = deauth_count(conn)
    print(f"deauth_flood detections in MSSQL before run: {before}")

    token = uuid.uuid4().hex[:8]
    stop = threading.Event()
    counters = {}

    def run_svc(name, svc, **kw):
        counters[name] = svc.run(stop_event=stop, offset="earliest",
                                 group_id=f"wids-{name}-{token}", **kw)

    extractor = FeatureExtractorService()
    inference = InferenceService()
    sink = DetectionSink(index_es=True)

    threads = [
        threading.Thread(target=run_svc, args=("sink", sink)),
        threading.Thread(target=run_svc, args=("inference", inference)),
        threading.Thread(target=run_svc, args=("extractor", extractor)),
    ]
    for t in threads:
        t.start()
    print("Pipeline services started; warming up...")
    time.sleep(3)

    # inject traffic: one attacker (deauth flood) + one normal sensor
    print("Injecting deauth flood (sensor-attack) + normal traffic (sensor-10)...")
    SensorAgent("sensor-attack", name="rogue", location="Floor 1", channel=6).run(
        SyntheticFrameSource(channel=6, attack="deauth_flood"), max_frames=160, rate_hz=0)
    SensorAgent("sensor-10", name="normal", location="Floor 2", channel=11).run(
        SyntheticFrameSource(channel=11), max_frames=80, rate_hz=0)

    print("Waiting for the pipeline to process...")
    time.sleep(10)
    stop.set()
    for t in threads:
        t.join(timeout=10)

    after = deauth_count(conn)
    print("\n  Pipeline throughput:", counters)
    cur = conn.cursor()
    cur.execute("""SELECT TOP 5 attack_type, sensor_id, score, confidence, explanation
                   FROM detection_events ORDER BY created_at DESC""")
    rows = cur.fetchall()
    print("\n  Recent detections (MSSQL detection_events)")
    print("  " + "-" * 78)
    for r in rows:
        print(f"  {r[0]:<16}{str(r[1]):<16}score={r[2]:<7}conf={r[3]:<6}{(r[4] or '')[:60]}")
    print("  " + "-" * 78)
    conn.close()

    ok = after > before
    print(f"\ndeauth_flood detections after run: {after} (was {before})")
    print("RESULT:", "PASS - deauth flood detected end-to-end and persisted"
          if ok else "FAIL - no new deauth_flood detection persisted")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
