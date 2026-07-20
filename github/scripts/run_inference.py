"""Run the inference service (feature-vectors -> detections)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from wids.streaming import InferenceService  # noqa: E402

if __name__ == "__main__":
    print("Inference service running (Ctrl+C to stop)...")
    try:
        InferenceService().run(offset="latest")
    except KeyboardInterrupt:
        print("\nStopped.")
