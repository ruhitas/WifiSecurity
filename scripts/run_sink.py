"""Run the detection sink (detections -> MSSQL + Elasticsearch + alerts)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from wids.streaming import DetectionSink  # noqa: E402

if __name__ == "__main__":
    print("Detection sink running (Ctrl+C to stop)...")
    try:
        DetectionSink().run(offset="latest")
    except KeyboardInterrupt:
        print("\nStopped.")
