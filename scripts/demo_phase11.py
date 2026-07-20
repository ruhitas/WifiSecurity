"""Phase 11: unseen-attack / unknown-attack anomaly detection.

Trains each detector on NORMAL traffic only, then measures how well it flags
attacks it never saw during training (all attack classes are 'unknown'). Reports
ROC-AUC plus detection rate (TPR) and false-positive rate at a threshold set to
the 95th percentile of normal training scores, and a per-attack breakdown.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np  # noqa: E402
from sklearn.metrics import roc_auc_score  # noqa: E402
from sklearn.model_selection import train_test_split  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402

from wids.feature_selection import load_dataset  # noqa: E402
from wids.feature_selection.selectors import drop_low_variance  # noqa: E402
from wids.anomaly import build_detectors  # noqa: E402

DATASETS = Path(__file__).resolve().parents[1] / "data" / "datasets"


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
    print(f"== Phase 11 unseen-attack anomaly detection ==\nDataset: {csv_path}")
    X, y = load_dataset(csv_path)
    X, _ = drop_low_variance(X)
    yv = y.values
    Xv = X.values.astype("float32")

    is_normal = np.array([str(v).lower() == "normal" for v in yv])
    Xn, Xa = Xv[is_normal], Xv[~is_normal]
    ya = yv[~is_normal]
    Xn_tr, Xn_te = train_test_split(Xn, test_size=0.3, random_state=42)

    scaler = StandardScaler().fit(Xn_tr)
    Xn_tr, Xn_te, Xa_s = scaler.transform(Xn_tr), scaler.transform(Xn_te), scaler.transform(Xa)

    # test set: normal-test (label 0) + all attacks (label 1)
    Xtest = np.vstack([Xn_te, Xa_s])
    ytest = np.concatenate([np.zeros(len(Xn_te)), np.ones(len(Xa_s))])

    print(f"Train on {len(Xn_tr)} NORMAL windows only · test: {len(Xn_te)} normal + {len(Xa_s)} attacks")
    print("\n  Detector          ROC-AUC   Detection%   FalsePos%")
    print("  " + "-" * 52)
    best = None
    for det in build_detectors(Xv.shape[1]):
        det.fit(Xn_tr)
        s_test = det.score(Xtest)
        s_train = det.score(Xn_tr)
        thr = np.percentile(s_train, 95)
        auc = roc_auc_score(ytest, s_test)
        tpr = float((det.score(Xa_s) > thr).mean())
        fpr = float((det.score(Xn_te) > thr).mean())
        print(f"  {det.name:<18}{auc:<10.4f}{tpr*100:<13.1f}{fpr*100:.1f}")
        if best is None or auc > best[1]:
            best = (det, auc)

    # per-attack breakdown for the best detector
    det = best[0]
    thr = np.percentile(det.score(Xn_tr), 95)
    print(f"\n  Per-attack detection rate ({det.name}, threshold=95th pct normal)")
    print("  " + "-" * 44)
    for cls in sorted(set(ya)):
        mask = ya == cls
        rate = float((det.score(Xa_s[mask]) > thr).mean())
        print(f"  {cls:<20}{rate*100:.1f}%")
    print("  " + "-" * 44)

    ok = best[1] > 0.8
    print(f"\nBest: {det.name} (ROC-AUC={best[1]:.4f})")
    print("RESULT:", "PASS - unknown attacks detected without training on any attack"
          if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
