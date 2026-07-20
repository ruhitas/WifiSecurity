"""Build the unified labeled dataset (Phase 7).

By default generates synthetic normal + multi-class attack windows and writes a
CSV + manifest under data/datasets/. Optionally append a real capture file
(e.g. AWID3) with --pcap and --pcap-label.

Examples:
    python scripts/build_dataset.py --windows 80 --window-size 60
    python scripts/build_dataset.py --pcap data/awid3_deauth.pcap --pcap-label deauth_flood
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from wids.dataset import DatasetBuilder, DEFAULT_CLASSES  # noqa: E402

OUT_DIR = Path(__file__).resolve().parents[1] / "data" / "datasets"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--windows", type=int, default=80, help="windows per generated class")
    ap.add_argument("--window-size", type=int, default=60, help="frames per window")
    ap.add_argument("--pcap", default=None, help="optional capture file to append")
    ap.add_argument("--pcap-label", default=None, help="label for --pcap windows")
    ap.add_argument("--name", default=None, help="output base name")
    args = ap.parse_args()

    b = DatasetBuilder(window_size=args.window_size)
    print(f"Generating {args.windows} windows x {len(DEFAULT_CLASSES)} classes "
          f"(window_size={args.window_size})...")
    b.add_generated(n_windows=args.windows)

    if args.pcap:
        if not args.pcap_label:
            raise SystemExit("--pcap-label is required with --pcap")
        print(f"Appending pcap {args.pcap} as label '{args.pcap_label}'...")
        b.add_pcap(args.pcap, args.pcap_label)

    stamp = time.strftime("%Y%m%d-%H%M%S")
    name = args.name or f"wids_dataset_{stamp}"
    csv_path = OUT_DIR / f"{name}.csv"
    b.write_csv(csv_path)
    mpath = b.write_manifest(csv_path, created_ts=time.time())

    s = b.summary()
    print("\n  Dataset built")
    print("  " + "-" * 50)
    print(f"  rows      : {s['rows']}")
    print(f"  features  : {s['features']}")
    print(f"  csv       : {csv_path}")
    print(f"  manifest  : {mpath}")
    print("  class distribution:")
    for label, c in s["classes"].items():
        print(f"      {label:<18}{c}")
    print("  " + "-" * 50)

    ok = s["rows"] > 0 and s["features"] >= 300 and len(s["classes"]) >= 2
    print("RESULT:", "PASS - labeled multi-class dataset ready for Phase 8/9"
          if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
