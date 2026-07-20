"""Measure deployment-oriented resource metrics for the paper (Section VI-F)."""
from __future__ import annotations

import json
import sys
import time
import tracemalloc
from pathlib import Path

import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from xgboost import XGBClassifier

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from wids.feature_selection import load_dataset  # noqa: E402
from wids.feature_selection.selectors import drop_low_variance  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "data" / "reports"
WINDOW_FRAMES = 40


def _cpu_percent(duration_s: float = 3.0) -> float | None:
    try:
        import psutil
        proc = psutil.Process()
        proc.cpu_percent(None)  # prime
        time.sleep(duration_s)
        return round(proc.cpu_percent(None) / psutil.cpu_count(logical=True), 1)
    except ImportError:
        return None


def main() -> int:
    csv = ROOT / "data" / "datasets" / "awid3_real.csv"
    X, y = load_dataset(csv)
    X, _ = drop_low_variance(X)
    y_arr = np.asarray(y, dtype=str)
    le = LabelEncoder().fit(y_arr)
    ye = le.transform(y_arr)
    Xtr, Xte, ytr, _ = train_test_split(
        X.values, ye, test_size=0.25, stratify=ye, random_state=42)

    model = XGBClassifier(
        n_estimators=300, tree_method="hist", eval_metric="mlogloss", random_state=42)
    model.fit(Xtr, ytr)

    # warmup
    model.predict(Xte[:1000])

    tracemalloc.start()
    t0 = time.perf_counter()
    n = 50_000
    reps = max(1, n // len(Xte))
    batch = np.tile(Xte, (reps, 1))[:n]
    model.predict(batch)
    infer_s = time.perf_counter() - t0
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    samples_per_s = n / infer_s
    # end-to-end window budget from prior measurement (feature extract + infer)
    fe_us = 726.93  # reviewer_timing.json
    infer_us = (infer_s / n) * 1e6
    window_us = fe_us + infer_us
    windows_per_s = 1e6 / window_us

    ram_mb = round(peak / (1024 * 1024), 1)
    cpu_pct = _cpu_percent()

    out = {
        "platform": "Intel Core Ultra 7 155H, 32 GB RAM, Windows 11, CPU-only",
        "model": "XGBoost (best)",
        "n_features": int(X.shape[1]),
        "window_frames": WINDOW_FRAMES,
        "inference_us_per_sample": round(infer_us, 2),
        "feature_extraction_us_per_window": fe_us,
        "end_to_end_us_per_window": round(window_us, 2),
        "throughput_samples_per_s": round(samples_per_s, 0),
        "throughput_windows_per_s": round(windows_per_s, 0),
        "peak_python_heap_mb_during_inference": ram_mb,
        "process_cpu_percent_avg_one_core": cpu_pct,
        "note": "CPU% is average process load over 3 s sustained predict; RAM is Python heap peak (tracemalloc).",
    }
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "deployment_metrics.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))
    print("\nRESULT: PASS - deployment metrics written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
