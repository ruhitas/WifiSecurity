"""Phase 12: explainable-AI reasoning reports for detections.

Trains a RandomForest on the dataset, then for one test instance per attack
class produces a reasoning report — SHAP feature contributions, confidence and a
plain-language explanation — plus the global feature importance.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np  # noqa: E402
from sklearn.ensemble import RandomForestClassifier  # noqa: E402
from sklearn.model_selection import train_test_split  # noqa: E402

from wids.feature_selection import load_dataset  # noqa: E402
from wids.feature_selection.selectors import drop_low_variance  # noqa: E402
from wids.xai import Explainer  # noqa: E402

DATASETS = Path(__file__).resolve().parents[1] / "data" / "datasets"
REPORTS = Path(__file__).resolve().parents[1] / "data" / "reports"


def latest_dataset():
    csvs = sorted(DATASETS.glob("*.csv"))
    if not csvs:
        raise SystemExit("No dataset. Run scripts/build_dataset.py first.")
    return csvs[-1]


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(); ap.add_argument("--csv", default=None)
    args = ap.parse_args()
    csv_path = Path(args.csv) if args.csv else latest_dataset()
    print(f"== Phase 12 explainable AI ==\nDataset: {csv_path}")
    X, y = load_dataset(csv_path)
    X, _ = drop_low_variance(X)
    names = list(X.columns)
    Xtr, Xte, ytr, yte = train_test_split(X.values, y.values, test_size=0.25,
                                          stratify=y.values, random_state=42)
    rf = RandomForestClassifier(n_estimators=300, random_state=42, n_jobs=-1).fit(Xtr, ytr)

    expl = Explainer(rf, names, list(rf.classes_), background=Xtr)
    print(f"Explainer backend: {expl.backend}\n")

    reports = {}
    print("  Reasoning reports (one instance per class)")
    print("  " + "-" * 80)
    for cls in sorted(set(yte)):
        idx = np.where(yte == cls)[0][0]
        rep = expl.reasoning_report(Xte[idx])
        reports[cls] = rep
        print(f"  [{cls}] {rep['explanation']}")
    print("  " + "-" * 80)

    gi = expl.global_importance(Xte[:500], top_k=10)  # sample for tractable SHAP
    print("\n  Global feature importance (top 10)")
    print("  " + "-" * 40)
    for f, v in gi:
        print(f"  {f:<28}{v}")
    print("  " + "-" * 40)

    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "xai_reports.json").write_text(
        json.dumps({"backend": expl.backend, "reports": reports,
                    "global_importance": gi}, indent=2), encoding="utf-8")
    print(f"\n  Wrote {REPORTS / 'xai_reports.json'}")

    ok = len(reports) >= 2 and all(r["explanation"] for r in reports.values())
    print("\nRESULT:", "PASS - reasoning reports + global importance produced"
          if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
