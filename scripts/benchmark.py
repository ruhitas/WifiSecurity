"""Phase 9: automated model benchmark on the Phase 7 dataset.

Trains 8-10 classical + boosting classifiers with stratified CV, ranks them by
macro-F1, reports training time and per-sample inference latency, builds a
confusion matrix for the best model, and writes a benchmark report.
"""
import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from wids.feature_selection import load_dataset  # noqa: E402
from wids.feature_selection.selectors import drop_low_variance  # noqa: E402
from wids.benchmark import benchmark, confusion_for_best  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DATASETS = ROOT / "data" / "datasets"
REPORTS = ROOT / "data" / "reports"


def latest_dataset():
    csvs = sorted(DATASETS.glob("*.csv"))
    if not csvs:
        raise SystemExit("No dataset found. Run scripts/build_dataset.py first.")
    return csvs[-1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=None)
    ap.add_argument("--selected", action="store_true", help="use Phase 8 selected features only")
    ap.add_argument("--cv", type=int, default=5)
    args = ap.parse_args()

    csv_path = Path(args.csv) if args.csv else latest_dataset()
    print(f"== Phase 9 model benchmark ==\nDataset: {csv_path}")
    X, y = load_dataset(csv_path)
    X, dropped = drop_low_variance(X)

    if args.selected:
        sel = json.loads((REPORTS / "selected_features.json").read_text())["selected"]
        sel = [c for c in sel if c in X.columns]
        X = X[sel]
        print(f"Using {len(sel)} Phase-8 selected features.")
    print(f"Features: {X.shape[1]} · samples: {X.shape[0]} · classes: {y.nunique()} · cv={args.cv}")

    print("\nTraining models (stratified cross-validation)...")
    results = benchmark(X, y, cv=args.cv)

    print("\n  Benchmark (ranked by macro-F1)")
    print("  " + "-" * 92)
    print(f"  {'MODEL':<20}{'ACC':<8}{'F1':<8}{'ROC-AUC':<9}{'PREC':<8}{'RECALL':<8}{'FIT(s)':<8}LATENCY(us/sample)")
    print("  " + "-" * 92)
    for r in results:
        if "error" in r:
            print(f"  {r['model']:<20}ERROR: {r['error']}")
            continue
        print(f"  {r['model']:<20}{r['accuracy']:<8}{r['f1']:<8}{r['roc_auc']:<9}"
              f"{r['precision']:<8}{r['recall']:<8}{r['fit_time_s']:<8}{r['latency_us']}")
    print("  " + "-" * 92)

    best = next((r for r in results if "error" not in r), None)
    cm_data = None
    if best:
        print(f"\nBest model: {best['model']} (F1={best['f1']}, ROC-AUC={best['roc_auc']})")
        cm, labels, report = confusion_for_best(X, y, best["model"])
        cm_data = {"model": best["model"], "labels": labels, "matrix": cm}
        print("\n  Confusion matrix (25% hold-out) — rows=true, cols=pred")
        header = "  true\\pred      " + "".join(f"{l[:8]:>10}" for l in labels)
        print(header)
        for i, row in enumerate(cm):
            print(f"  {labels[i][:14]:<14}" + "".join(f"{v:>10}" for v in row))
        print(f"\n  macro avg F1 (hold-out): {report['macro avg']['f1-score']:.4f}")

    # write report
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "benchmark.json").write_text(
        json.dumps({"dataset": csv_path.name, "features": X.shape[1],
                    "results": results, "confusion": cm_data}, indent=2), encoding="utf-8")
    with open(REPORTS / "benchmark.csv", "w", newline="", encoding="utf-8") as f:
        cols = ["model", "accuracy", "f1", "roc_auc", "precision", "recall", "fit_time_s", "latency_us"]
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in results:
            w.writerow(r)
    print(f"\n  Wrote {REPORTS / 'benchmark.json'} and benchmark.csv")

    ok = best is not None and best["f1"] > 0
    print("\nRESULT:", "PASS - benchmark table + confusion matrix produced"
          if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
