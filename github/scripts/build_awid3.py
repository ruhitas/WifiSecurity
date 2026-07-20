"""Build a standardized, class-balanced dataset from AWID3 CSVs.

Works on the reduced AWID3_5csv set or the full 43 GB AWID3_archive/CSV (use
--files-per-cat to bound I/O on the archive).
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from wids.dataset.awid3 import build_awid3_dataset  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(ROOT / "AWID3_5csv"),
                    help="folder of AWID3 CSVs (e.g. AWID3_archive/CSV)")
    ap.add_argument("--out", default=str(ROOT / "data" / "datasets" / "awid3_real.csv"))
    ap.add_argument("--normal-cap", type=int, default=20000)
    ap.add_argument("--attack-cap", type=int, default=8000)
    ap.add_argument("--files-per-cat", type=int, default=None,
                    help="max CSV files read per category folder (bounds I/O)")
    args = ap.parse_args()

    print(f"== Building AWID3 dataset from {args.root} ==")
    info = build_awid3_dataset(args.root, args.out, normal_cap=args.normal_cap,
                               attack_cap=args.attack_cap,
                               files_per_category=args.files_per_cat)
    print(f"\n  rows      : {info['rows']}")
    print(f"  features  : {info['features']} (dropped {info['dropped_constant']} constant)")
    print(f"  csv       : {info['csv']}")
    print("  class distribution:")
    for lbl, c in sorted(info["classes"].items(), key=lambda x: -x[1]):
        print(f"      {lbl:<20}{c}")
    ok = info["rows"] > 0 and info["features"] >= 5 and len(info["classes"]) >= 2
    print("\nRESULT:", "PASS - AWID3 dataset ready" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
