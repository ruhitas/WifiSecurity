"""Analyze ANY labeled CSV dataset (not only AWID3).

Point it at any CSV that has a label/class column and it will:
  * auto-detect the label column (or use --label),
  * keep numeric features and one-hot encode small categorical columns,
  * drop zero-variance and obvious id/time/meta columns,
  * benchmark the same model suite used for AWID3 (stratified CV),
  * print a ranked table + confusion matrix for the best model,
  * write a report to data/reports/analyze_<name>.json.

Examples:
    python scripts/analyze_dataset.py --csv data/datasets/awid3_real.csv
    python scripts/analyze_dataset.py --csv mydata.csv --label attack_type --cv 5
    python scripts/analyze_dataset.py --csv capture_features.csv --label label
"""
import argparse
import json
import re
import sys
from pathlib import Path

# make stdout robust to non-ASCII class names (e.g. CICIDS "Web Attack" labels)
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from wids.benchmark import benchmark, confusion_for_best, FAST_MODELS  # noqa: E402
from wids.feature_selection.selectors import drop_low_variance  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "data" / "reports"

# identifier tokens: a column is meta if one of its tokens (split on non-alnum)
# is in this set. Token-based so "srcport"/"dstport" survive but "wlan.sa" and
# "sensor_id" are dropped. MAC/address text columns are dropped later by the
# categorical-cardinality filter anyway.
META_TOKENS = {"id", "index", "unnamed", "timestamp", "ts", "date", "datetime",
               "sensor", "session", "source", "bssid", "mac", "addr"}
LABEL_HINTS = ("label", "class", "attack", "category", "target", "y", "attack_type",
               "attack_cat", "marker")


def _is_meta(col: str) -> bool:
    tokens = set(re.split(r"[^a-z0-9]+", col.lower()))
    return bool(tokens & META_TOKENS)


def read_any(path: Path) -> pd.DataFrame:
    """Read a .parquet or .csv file into a DataFrame (columns stripped)."""
    if path.suffix.lower() in (".parquet", ".pq"):
        df = pd.read_parquet(path)
    else:
        # AWID and some corpora mark missing values with '?'
        df = pd.read_csv(path, low_memory=False, na_values=["?"])
    df.columns = df.columns.astype(str).str.strip()
    return df


def list_data_files(folder: Path) -> list[Path]:
    files = []
    for ext in ("*.csv", "*.parquet", "*.pq"):
        files.extend(folder.glob(ext))
    return sorted(files)


def detect_label(df: pd.DataFrame, explicit: str | None) -> str:
    if explicit:
        if explicit not in df.columns:
            raise SystemExit(f"--label '{explicit}' not found. Columns: {list(df.columns)[:20]} ...")
        return explicit
    lowered = {c.lower(): c for c in df.columns}
    for hint in LABEL_HINTS:
        if hint in lowered:
            return lowered[hint]
    # fall back to the last column
    print(f"  (no obvious label column; using the last column '{df.columns[-1]}')")
    return df.columns[-1]


def build_xy(df: pd.DataFrame, label_col: str, max_card: int = 40):
    y = df[label_col].astype(str)
    X = df.drop(columns=[label_col])

    # drop obvious meta / identifier / free-text columns
    drop = [c for c in X.columns if _is_meta(c)]
    if drop:
        X = X.drop(columns=drop)
        print(f"  dropped {len(drop)} id/time/meta columns: {', '.join(drop[:8])}"
              + (" ..." if len(drop) > 8 else ""))

    num = X.select_dtypes(include=[np.number]).replace([np.inf, -np.inf], np.nan)
    obj = X.select_dtypes(exclude=[np.number])
    # one-hot encode small-cardinality categoricals; drop huge ones
    keep_obj = [c for c in obj.columns if obj[c].nunique() <= max_card]
    skip_obj = [c for c in obj.columns if c not in keep_obj]
    if skip_obj:
        print(f"  skipped {len(skip_obj)} high-cardinality text columns: {', '.join(skip_obj[:8])}"
              + (" ..." if len(skip_obj) > 8 else ""))
    dummies = pd.get_dummies(obj[keep_obj], dummy_na=False) if keep_obj else pd.DataFrame(index=X.index)
    X = pd.concat([num, dummies], axis=1).fillna(0.0)
    return X, y


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True,
                    help="path to a dataset CSV, or a folder of CSVs to concatenate")
    ap.add_argument("--label", default=None, help="name of the label column (auto-detected if omitted)")
    ap.add_argument("--cv", type=int, default=5)
    ap.add_argument("--sample", type=int, default=0,
                    help="cap total rows (stratified per file); 0 = use all rows")
    ap.add_argument("--min-per-class", type=int, default=10,
                    help="drop classes with fewer than this many samples")
    ap.add_argument("--fast", action="store_true",
                    help="only fast tree/boosting models (for very large datasets)")
    args = ap.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.exists():
        raise SystemExit(f"ERROR: path not found: {csv_path}")

    print(f"== Generic dataset analysis ==\nDataset: {csv_path}")
    if csv_path.is_dir():
        files = list_data_files(csv_path)
        if not files:
            raise SystemExit(f"ERROR: no .csv/.parquet files in folder {csv_path}")
        per = (args.sample // len(files)) if args.sample else None
        parts = []
        for fp in files:
            d = read_any(fp)
            if per and len(d) > per:
                d = d.sample(n=per, random_state=1)
            parts.append(d)
            print(f"  {fp.name}: {len(d)} rows")
        df = pd.concat(parts, ignore_index=True)
        print(f"  combined: {len(df)} rows, {df.shape[1]} columns")
    else:
        df = read_any(csv_path)
        if args.sample and len(df) > args.sample:
            df = df.sample(n=args.sample, random_state=1)
            print(f"  sampled {len(df)} of the rows")

    label_col = detect_label(df, args.label)
    print(f"Label column: '{label_col}'")

    X, y = build_xy(df, label_col)

    # drop tiny classes that break stratified CV
    counts = y.value_counts()
    small = counts[counts < args.min_per_class].index.tolist()
    if small:
        mask = ~y.isin(small)
        X, y = X[mask], y[mask]
        print(f"  dropped {len(small)} rare class(es) < {args.min_per_class} samples: "
              f"{', '.join(map(str, small[:8]))}" + (" ..." if len(small) > 8 else ""))

    X, dropped = drop_low_variance(X)
    n_classes = y.nunique()
    print(f"Features: {X.shape[1]} · samples: {X.shape[0]} · classes: {n_classes} · cv={args.cv}")
    if X.shape[1] == 0:
        raise SystemExit("ERROR: no usable numeric/categorical features after cleaning.")
    if n_classes < 2:
        raise SystemExit("ERROR: need at least 2 classes to train a classifier.")

    include = FAST_MODELS if args.fast else None
    if args.fast:
        print(f"  fast mode: only {', '.join(FAST_MODELS)}")
    print("\nTraining models (stratified cross-validation)...")
    results = benchmark(X, y, cv=args.cv, include=include)

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
        print(f"  macro avg F1 (25% hold-out): {report['macro avg']['f1-score']:.4f}")

    REPORTS.mkdir(parents=True, exist_ok=True)
    out = REPORTS / f"analyze_{csv_path.stem}.json"
    out.write_text(json.dumps({"dataset": csv_path.name, "label_column": label_col,
                               "features": X.shape[1], "classes": int(n_classes),
                               "results": results, "confusion": cm_data}, indent=2),
                   encoding="utf-8")
    print(f"\n  Wrote {out}")
    ok = best is not None and best["f1"] > 0
    print("\nRESULT:", "PASS - dataset analyzed" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
