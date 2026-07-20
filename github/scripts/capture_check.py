"""Report 802.11 capture capability on this host."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from wids.sensors.capture import capability_report  # noqa: E402


def main():
    info = capability_report()
    print("\n  802.11 capture capability")
    print("  " + "-" * 60)
    print(f"  scapy installed : {info.get('scapy')}  (v{info.get('scapy_version','?')})")
    print(f"  platform        : {info.get('platform','?')}")
    ifaces = info.get("interfaces", [])
    print(f"  interfaces ({len(ifaces)}):")
    for i in ifaces:
        print(f"      - {i}")
    print("  " + "-" * 60)
    print("  note:", info.get("note", ""))
    print()


if __name__ == "__main__":
    main()
