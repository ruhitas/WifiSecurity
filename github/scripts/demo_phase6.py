"""Phase 6 verification: 300+ feature extraction.

Builds a 'normal' window and a 'deauth flood' window from the frame sources,
computes the full feature vector for each, and checks:
  * the vector has >= 300 features
  * the keys the inference stub needs are present
  * discriminative features clearly separate normal vs attack
"""
import sys
from collections import Counter
from itertools import islice
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from wids.sensors.frames import SyntheticFrameSource  # noqa: E402
from wids.streaming.features import compute_features, feature_names  # noqa: E402

WINDOW = 200


def take(source, n):
    return list(islice(source.iterate(), n))


def category(name: str) -> str:
    for q in ("rssi", "length", "ifd", "src_rssi_mean", "src_count", "dst_count",
              "bssid_count", "beacon_interval", "seq_gap", "pair_count",
              "src_degree", "bssid_degree"):
        if name.startswith(q + "_"):
            return f"stats:{q}"
    if name.startswith("sub_"):
        return "subtype"
    if name.startswith("graph_"):
        return "graph"
    if name.endswith("_entropy"):
        return "entropy"
    if "oui" in name:
        return "vendor/oui"
    return "other"


def main() -> int:
    print("== Phase 6 feature-extraction verification ==")
    normal = compute_features(take(SyntheticFrameSource(channel=6, seed=1), WINDOW))
    attack = compute_features(take(SyntheticFrameSource(channel=6, seed=1, attack="deauth_flood"), WINDOW))

    names = feature_names()
    total = len(names)
    print(f"\nTotal features produced: {total}")

    cats = Counter(category(n) for n in names)
    print("\n  Features by category")
    print("  " + "-" * 40)
    for cat, c in sorted(cats.items(), key=lambda x: -x[1]):
        print(f"  {cat:<22}{c}")
    print("  " + "-" * 40)

    needed = ["frame_count", "deauth_count", "deauth_rate", "disassoc_count", "retry_rate"]
    missing = [k for k in needed if k not in attack]
    print("\nInference-required keys present:", "yes" if not missing else f"MISSING {missing}")

    print("\n  Discriminative features (normal vs deauth-flood)")
    print("  " + "-" * 60)
    for k in ["deauth_rate", "sub_deauth_rate", "subtype_entropy",
              "mgmt_rate", "graph_mobility_rate", "rssi_std"]:
        print(f"  {k:<24}normal={normal.get(k):<12}attack={attack.get(k)}")
    print("  " + "-" * 60)

    ok = (total >= 300 and not missing
          and attack["deauth_rate"] > 0.5 and normal["deauth_rate"] < 0.3)
    print("\nRESULT:", f"PASS - {total} features, attack clearly separated"
          if ok else "FAIL - check feature count / separation")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
