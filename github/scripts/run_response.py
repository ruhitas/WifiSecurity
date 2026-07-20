"""Run the autonomous response engine (detections -> policy -> actions)."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from wids.response import ResponseEngine  # noqa: E402

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="disable dry-run (requires real endpoints)")
    args = ap.parse_args()
    mode = "LIVE" if args.live else "dry-run"
    print(f"Response engine running ({mode}) — Ctrl+C to stop...")
    try:
        ResponseEngine(dry_run=not args.live).run(offset="latest")
    except KeyboardInterrupt:
        print("\nStopped.")
