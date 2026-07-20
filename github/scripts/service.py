"""Container entrypoint: run one pipeline service selected by $WIDS_SERVICE.

    WIDS_SERVICE = feature-extractor | inference | response | sink
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def main():
    name = os.getenv("WIDS_SERVICE") or (sys.argv[1] if len(sys.argv) > 1 else "")
    print(f"[service] starting '{name}'")
    if name == "feature-extractor":
        from wids.streaming import FeatureExtractorService
        FeatureExtractorService().run(offset="latest")
    elif name == "inference":
        from wids.streaming import InferenceService
        InferenceService().run(offset="latest")
    elif name == "sink":
        from wids.streaming import DetectionSink
        DetectionSink().run(offset="latest")
    elif name == "response":
        from wids.response import ResponseEngine
        ResponseEngine(dry_run=os.getenv("WIDS_RESPONSE_LIVE", "0") != "1").run(offset="latest")
    else:
        raise SystemExit(f"unknown WIDS_SERVICE '{name}' "
                         "(feature-extractor|inference|response|sink)")


if __name__ == "__main__":
    main()
