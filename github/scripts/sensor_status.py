"""Print the sensor registry with live (Redis heartbeat) status."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from wids.sensors import SensorRegistry  # noqa: E402


def main():
    reg = SensorRegistry()
    rows = reg.list_status()
    reg.close()
    if not rows:
        print("No sensors registered yet.")
        return
    print(f"\n  {'SENSOR':<14}{'ONLINE':<8}{'STATUS':<10}{'LOCATION':<16}LAST SEEN (UTC)")
    print("  " + "-" * 74)
    for r in rows:
        online = "yes" if r["online"] else "no"
        ls = r["last_seen"].strftime("%Y-%m-%d %H:%M:%S") if r["last_seen"] else "-"
        print(f"  {r['sensor_id']:<14}{online:<8}{(r['status'] or '-'):<10}"
              f"{(r['location'] or '-'):<16}{ls}")
    print()


if __name__ == "__main__":
    main()
