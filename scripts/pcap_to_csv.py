"""Convert a captured 802.11 .pcap/.pcapng into a windowed feature CSV.

This bridges real capture (Wireshark, tcpdump, airodump-ng, ...) to the
analysis tools: it reads the capture with Scapy, groups frames into tumbling
windows, computes the same 300+ feature vector the live pipeline uses
(wids.streaming.features.compute_features), and writes one row per window.

You can then:
  * label it (add a 'label' column, e.g. 'normal' or an attack name), and
  * analyze it with:  python scripts/analyze_dataset.py --csv <out>.csv

Build a labeled dataset by capturing normal and attack traffic separately and
tagging each file with --label:
    python scripts/pcap_to_csv.py --pcap normal.pcap --label normal   --out normal.csv
    python scripts/pcap_to_csv.py --pcap deauth.pcap --label deauth   --out deauth.csv
then concatenate the CSVs.

Requires the capture extras:  pip install -r requirements-capture.txt
Live 802.11 capture needs a monitor-mode-capable adapter (see the README).
"""
import argparse
import csv
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from wids.sensors.capture import PcapReplaySource  # noqa: E402
from wids.streaming.features import compute_features  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pcap", required=True, help="input .pcap/.pcapng file")
    ap.add_argument("--out", required=True, help="output features CSV")
    ap.add_argument("--window", type=int, default=40, help="frames per window (default 40)")
    ap.add_argument("--label", default=None, help="optional label written to every row")
    ap.add_argument("--min-frames", type=int, default=5,
                    help="emit a trailing partial window only if it has this many frames")
    args = ap.parse_args()

    pcap = Path(args.pcap)
    if not pcap.exists():
        raise SystemExit(f"ERROR: pcap not found: {pcap}")

    print(f"== pcap -> features ==\nInput : {pcap}\nWindow: {args.window} frames"
          + (f"\nLabel : {args.label}" if args.label else ""))
    try:
        src = PcapReplaySource(str(pcap), loop=False)
    except RuntimeError as e:
        raise SystemExit(f"ERROR: {e}")

    rows = []
    buf = []
    total = 0
    for frame in src.iterate():
        total += 1
        buf.append(frame)
        if len(buf) >= args.window:
            rows.append(compute_features(buf))
            buf = []
    if len(buf) >= args.min_frames:
        rows.append(compute_features(buf))

    if not rows:
        raise SystemExit(
            "ERROR: no 802.11 frames found. The capture may not contain Dot11 "
            "frames (monitor-mode capture is required to record 802.11 headers).")

    # union of all feature keys (compute_features is dynamic)
    keys = []
    seen = set()
    for r in rows:
        for k in r:
            if k not in seen:
                seen.add(k); keys.append(k)
    if args.label:
        keys.append("label")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            if args.label:
                r = {**r, "label": args.label}
            w.writerow(r)

    print(f"\n  Parsed {total} 802.11 frames -> {len(rows)} feature windows "
          f"({len(keys)} columns)")
    print(f"  Wrote {out}")
    print("\nRESULT: PASS - feature CSV produced")
    print("Next: label it (add a 'label' column) then run "
          "scripts/analyze_dataset.py --csv " + str(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
