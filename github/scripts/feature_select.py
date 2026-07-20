"""Phase 8: run feature-selection methods and produce a consensus + report.

Compares Mutual Information, ANOVA-F, Random-Forest importance, Permutation
importance, L1/LASSO and RFE on the Phase 7 dataset, prints per-method top
features and a consensus ranking, reports the PCA dimensionality, and writes a
report + selected-feature subset for Phase 9/10.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from wids.feature_selection import load_dataset, run_all_methods, consensus_ranking  # noqa: E402
from wids.feature_selection.selectors import (drop_low_variance, rank_of,  # noqa: E402
                                              pca_components_for_variance)

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
    ap.add_argument("--select", type=int, default=40, help="consensus features to keep")
    args = ap.parse_args()

    csv_path = Path(args.csv) if args.csv else latest_dataset()
    print(f"== Phase 8 feature selection ==\nDataset: {csv_path}")

    X, y = load_dataset(csv_path)
    X, dropped = drop_low_variance(X)
    print(f"Features: {X.shape[1]} (dropped {len(dropped)} zero-variance) · "
          f"samples: {X.shape[0]} · classes: {y.nunique()}")

    print("\nRunning methods (mutual_info, anova_f, rf_importance, permutation, lasso_l1, rfe)...")
    results = run_all_methods(X, y)

    # per-method top 8
    print("\n  Top features per method")
    print("  " + "-" * 68)
    for m, scores in results.items():
        top = sorted(scores, key=lambda f: scores[f], reverse=True)[:8]
        print(f"  {m:<14}{', '.join(top)}")
    print("  " + "-" * 68)

    consensus = consensus_ranking(results)
    print("\n  Consensus ranking (top 15)")
    print("  " + "-" * 58)
    print(f"  {'FEATURE':<34}{'AVG_RANK':<10}VOTES")
    print("  " + "-" * 58)
    for r in consensus[:15]:
        print(f"  {r['feature']:<34}{r['avg_rank']:<10}{r['votes']}/{len(results)}")
    print("  " + "-" * 58)

    n_pca, var = pca_components_for_variance(X, 0.95)
    print(f"\n  PCA: {n_pca} components explain {var:.1%} of variance "
          f"(from {X.shape[1]} features)")

    # write outputs
    REPORTS.mkdir(parents=True, exist_ok=True)
    selected = [r["feature"] for r in consensus[:args.select]]
    report = {
        "dataset": csv_path.name,
        "n_features": X.shape[1],
        "n_samples": int(X.shape[0]),
        "n_classes": int(y.nunique()),
        "dropped_zero_variance": dropped,
        "pca_components_95": n_pca,
        "per_method_top30": {m: sorted(s, key=lambda f: s[f], reverse=True)[:30]
                             for m, s in results.items()},
        "consensus": consensus,
    }
    (REPORTS / "feature_selection_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (REPORTS / "selected_features.json").write_text(
        json.dumps({"selected": selected, "count": len(selected)}, indent=2), encoding="utf-8")
    print(f"\n  Wrote {REPORTS / 'feature_selection_report.json'}")
    print(f"  Wrote {REPORTS / 'selected_features.json'} ({len(selected)} features)")

    ok = len(consensus) > 0 and len(selected) == args.select
    print("\nRESULT:", "PASS - consensus feature ranking + subset produced"
          if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
