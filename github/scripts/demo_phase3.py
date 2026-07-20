"""Phase 3 end-to-end demo / verification of the multi-sensor fabric.

Starts N simulated sensors that each register, open a session, and stream
synthetic frames to Kafka; then a central consumer reads wids.raw-frames and
tallies frames per sensor — proving many sensors feed one server. Finally it
prints the sensor registry status.
"""
import json
import sys
import threading
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kafka import KafkaConsumer  # noqa: E402
from wids.config import settings  # noqa: E402
from wids.schema import ensure_schema  # noqa: E402
from wids.sensors import SensorAgent, SensorRegistry  # noqa: E402
from wids.sensors.frames import SyntheticFrameSource  # noqa: E402
from wids.sensors.agent import RAW_TOPIC  # noqa: E402

SENSORS = [
    ("sensor-01", "Floor 1 - North", 1),
    ("sensor-02", "Floor 1 - South", 6),
    ("sensor-03", "Floor 2 - Core", 11),
]
FRAMES_EACH = 100


def run_agent(sensor_id, location, channel, results):
    agent = SensorAgent(sensor_id, name=sensor_id, location=location,
                        nic_chipset="synthetic", channel=channel)
    n = agent.run(SyntheticFrameSource(channel=channel, seed=hash(sensor_id) & 0xFFFF),
                  max_frames=FRAMES_EACH, rate_hz=200)
    results[sensor_id] = n


def main() -> int:
    print("== Phase 3 multi-sensor demo ==")
    tables = ensure_schema()
    print("Schema ready:", ", ".join(tables))

    # 1. run the sensor fleet (threads = simulated distributed sensors)
    print(f"\nStarting {len(SENSORS)} sensors, {FRAMES_EACH} frames each ...")
    results, threads = {}, []
    for sid, loc, ch in SENSORS:
        t = threading.Thread(target=run_agent, args=(sid, loc, ch, results))
        t.start()
        threads.append(t)
    for t in threads:
        t.join()
    sent = sum(results.values())
    print("Frames sent per sensor:", results, "-> total", sent)

    # 2. central consumer: read everything and tally per sensor
    print(f"\nConsuming '{RAW_TOPIC}' at the central server ...")
    consumer = KafkaConsumer(
        RAW_TOPIC,
        bootstrap_servers=settings.kafka_bootstrap,
        group_id="wids-phase3-demo",
        auto_offset_reset="earliest",
        enable_auto_commit=False,
        consumer_timeout_ms=5000,
        value_deserializer=lambda b: json.loads(b.decode("utf-8")),
    )
    per_sensor = Counter()
    channels = {}
    total = 0
    for msg in consumer:
        v = msg.value
        per_sensor[v.get("sensor_id", "?")] += 1
        channels[v.get("sensor_id")] = v.get("channel")
        total += 1
    consumer.close()

    print("\n  Central server — frames received per sensor")
    print("  " + "-" * 50)
    print(f"  {'SENSOR':<14}{'CHANNEL':<10}FRAMES")
    print("  " + "-" * 50)
    for sid, _, _ in SENSORS:
        print(f"  {sid:<14}{str(channels.get(sid,'-')):<10}{per_sensor.get(sid,0)}")
    print("  " + "-" * 50)
    print(f"  total received: {total}")

    # 3. registry status
    reg = SensorRegistry()
    rows = reg.list_status()
    reg.close()
    print("\n  Sensor registry (MSSQL WirelesSecureDB)")
    print("  " + "-" * 50)
    for r in rows:
        print(f"  {r['sensor_id']:<14}status={r['status'] or '-':<9}online={r['online']}")
    print("  " + "-" * 50)

    ok = all(per_sensor.get(sid, 0) > 0 for sid, _, _ in SENSORS)
    print("\nRESULT:", "PASS - all sensors delivered to the central server"
          if ok else "FAIL - some sensors delivered nothing")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
