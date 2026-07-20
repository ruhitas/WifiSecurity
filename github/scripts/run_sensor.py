"""Run a single wireless sensor node.

Sources:
    synthetic  - generated 802.11-like frames (default; no hardware needed)
    replay     - replay a .pcap/.pcapng file (--pcap PATH)
    capture    - live monitor-mode capture (--iface NAME; needs capable NIC)

Examples:
    python scripts/run_sensor.py --id sensor-01 --source synthetic --rate 20
    python scripts/run_sensor.py --id sensor-01 --source replay --pcap data/sample.pcap
    python scripts/run_sensor.py --id sensor-01 --source capture --iface "Wi-Fi"
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from wids.sensors import SensorAgent  # noqa: E402
from wids.sensors.frames import SyntheticFrameSource  # noqa: E402


def build_source(args):
    if args.source == "synthetic":
        return SyntheticFrameSource(channel=args.channel)
    if args.source == "replay":
        if not args.pcap:
            raise SystemExit("--pcap is required for --source replay")
        from wids.sensors.capture import PcapReplaySource
        return PcapReplaySource(args.pcap, loop=args.loop)
    if args.source == "capture":
        if not args.iface:
            raise SystemExit("--iface is required for --source capture")
        from wids.sensors.capture import CaptureFrameSource
        return CaptureFrameSource(args.iface, monitor=not args.no_monitor)
    raise SystemExit(f"unknown source: {args.source}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", required=True)
    ap.add_argument("--name", default=None)
    ap.add_argument("--location", default=None)
    ap.add_argument("--channel", type=int, default=6)
    ap.add_argument("--source", choices=["synthetic", "replay", "capture"], default="synthetic")
    ap.add_argument("--pcap", default=None)
    ap.add_argument("--iface", default=None)
    ap.add_argument("--loop", action="store_true", help="replay: loop the file")
    ap.add_argument("--no-monitor", action="store_true", help="capture: disable monitor mode")
    ap.add_argument("--rate", type=float, default=20.0, help="max frames/second (0 = unlimited)")
    ap.add_argument("--max", type=int, default=None, help="stop after N frames")
    args = ap.parse_args()

    source = build_source(args)
    nic = {"synthetic": "synthetic", "replay": "pcap", "capture": args.iface}[args.source]
    agent = SensorAgent(args.id, args.name, args.location, nic, args.channel)
    print(f"Starting {args.id} [source={args.source}] (Ctrl+C to stop)...")
    try:
        n = agent.run(source, max_frames=args.max, rate_hz=args.rate, verbose=True)
        print(f"Stopped. Sent {n} frames.")
    except KeyboardInterrupt:
        print("\nInterrupted.")


if __name__ == "__main__":
    main()
