"""Run the feature-extraction service (raw-frames -> feature-vectors)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from wids.streaming import FeatureExtractorService  # noqa: E402

if __name__ == "__main__":
    print("Feature extractor running (Ctrl+C to stop)...")
    try:
        FeatureExtractorService().run(offset="latest")
    except KeyboardInterrupt:
        print("\nStopped.")
