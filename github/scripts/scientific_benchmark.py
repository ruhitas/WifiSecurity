"""Phase 16: publication-quality scientific figures from the real AWID3 results.

Generates ROC / PR curves, a normalized confusion matrix, per-class F1, model
comparison, feature importance and an ablation curve, plus measured inference
latency and throughput. Figures are colorblind-safe (Okabe-Ito categorical,
single-hue sequential) and saved as PNGs for the paper (Phase 17).
"""
import json
import sys
import time
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from sklearn.metrics import (auc, classification_report, confusion_matrix,  # noqa: E402
                             precision_recall_curve, roc_curve)
from sklearn.model_selection import train_test_split  # noqa: E402
from sklearn.preprocessing import LabelEncoder, label_binarize  # noqa: E402
from xgboost import XGBClassifier  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from wids.feature_selection import load_dataset  # noqa: E402
from wids.feature_selection.selectors import drop_low_variance  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FIG = ROOT / "data" / "reports" / "figures"
FIG.mkdir(parents=True, exist_ok=True)

OKABE = ["#0072B2", "#E69F00", "#009E73", "#D55E00", "#CC79A7",
         "#56B4E9", "#F0E442", "#000000"]
BLUE = "#0072B2"

plt.rcParams.update({
    "figure.dpi": 300, "savefig.dpi": 300, "font.size": 11,
    "axes.titlesize": 13, "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.alpha": 0.25, "figure.autolayout": True,
})


def train_model(Xtr, ytr, n=300):
    m = XGBClassifier(n_estimators=n, tree_method="hist", eval_metric="mlogloss",
                      random_state=42)
    m.fit(Xtr, ytr)
    return m


def main():
    csv = ROOT / "data" / "datasets" / "awid3_real.csv"
    print(f"== Phase 16 scientific benchmark ==\nDataset: {csv}")
    X, y = load_dataset(csv)
    X, _ = drop_low_variance(X)
    names = list(X.columns)
    le = LabelEncoder().fit(y)
    classes = list(le.classes_)
    ye = le.transform(y)
    Xtr, Xte, ytr, yte = train_test_split(X.values, ye, test_size=0.25,
                                          stratify=ye, random_state=42)
    print(f"features={X.shape[1]} classes={len(classes)} train={len(ytr)} test={len(yte)}")

    model = train_model(Xtr, ytr)
    proba = model.predict_proba(Xte)
    pred = proba.argmax(1)

    # --- inference latency / throughput ---
    t0 = time.perf_counter(); model.predict(Xte); dt = time.perf_counter() - t0
    latency_us = dt / len(Xte) * 1e6
    throughput = len(Xte) / dt

    # === Figure 1: confusion matrix (normalized) ===
    cm = confusion_matrix(yte, pred, normalize="true")
    fig, ax = plt.subplots(figsize=(8, 7))
    im = ax.imshow(cm, cmap="Blues", vmin=0, vmax=1)
    ax.set_xticks(range(len(classes))); ax.set_yticks(range(len(classes)))
    ax.set_xticklabels(classes, rotation=90); ax.set_yticklabels(classes)
    ax.set_xlabel("Predicted"); ax.set_ylabel("True")
    ax.set_title("AWID3 confusion matrix (XGBoost, row-normalized)")
    for i in range(len(classes)):
        for j in range(len(classes)):
            if cm[i, j] >= 0.01:
                ax.text(j, i, f"{cm[i,j]:.2f}", ha="center", va="center",
                        fontsize=6, color="white" if cm[i, j] > 0.5 else "#333")
    fig.colorbar(im, fraction=0.046, pad=0.04)
    ax.grid(False)
    fig.savefig(FIG / "fig_confusion_matrix.png", bbox_inches="tight"); plt.close(fig)

    # === Figures 2 & 3: ROC and PR (OvR, micro + macro + per-class) ===
    Y = label_binarize(yte, classes=range(len(classes)))
    # ROC
    fig, ax = plt.subplots(figsize=(7, 6))
    aucs = []
    grid = np.linspace(0, 1, 200); mean_tpr = np.zeros_like(grid)
    for i in range(len(classes)):
        fpr, tpr, _ = roc_curve(Y[:, i], proba[:, i]); a = auc(fpr, tpr); aucs.append(a)
        ax.plot(fpr, tpr, color="#999999", alpha=0.35, lw=0.8)
        mean_tpr += np.interp(grid, fpr, tpr)
    mean_tpr /= len(classes)
    fpr_mi, tpr_mi, _ = roc_curve(Y.ravel(), proba.ravel()); auc_mi = auc(fpr_mi, tpr_mi)
    ax.plot(fpr_mi, tpr_mi, color=OKABE[0], lw=2.2, label=f"micro-average (AUC={auc_mi:.4f})")
    ax.plot(grid, mean_tpr, color=OKABE[3], lw=2.2, ls="--",
            label=f"macro-average (AUC={np.mean(aucs):.4f})")
    ax.plot([0, 1], [0, 1], color="#bbbbbb", lw=1, ls=":")
    ax.set_xlabel("False positive rate"); ax.set_ylabel("True positive rate")
    ax.set_title(f"ROC — AWID3 14-class (per-class AUC {min(aucs):.3f}–{max(aucs):.3f})")
    ax.legend(loc="lower right", frameon=False)
    fig.savefig(FIG / "fig_roc_curves.png", bbox_inches="tight"); plt.close(fig)
    # PR
    fig, ax = plt.subplots(figsize=(7, 6))
    for i in range(len(classes)):
        pr, rc, _ = precision_recall_curve(Y[:, i], proba[:, i])
        ax.plot(rc, pr, color="#999999", alpha=0.35, lw=0.8)
    pr_mi, rc_mi, _ = precision_recall_curve(Y.ravel(), proba.ravel())
    ax.plot(rc_mi, pr_mi, color=OKABE[0], lw=2.2, label=f"micro-average (AP={auc(rc_mi, pr_mi):.4f})")
    ax.set_xlabel("Recall"); ax.set_ylabel("Precision")
    ax.set_title("Precision–Recall — AWID3 14-class")
    ax.legend(loc="lower left", frameon=False)
    fig.savefig(FIG / "fig_pr_curves.png", bbox_inches="tight"); plt.close(fig)

    # === Figure 4: per-class F1 ===
    rep = classification_report(yte, pred, target_names=classes, output_dict=True,
                                zero_division=0)
    order = sorted(classes, key=lambda c: rep[c]["f1-score"])
    vals = [rep[c]["f1-score"] for c in order]
    fig, ax = plt.subplots(figsize=(7, 6))
    ax.barh(order, vals, color=BLUE, height=0.7)
    for i, v in enumerate(vals):
        ax.text(v + 0.005, i, f"{v:.3f}", va="center", fontsize=8)
    ax.set_xlim(0, 1.05); ax.set_xlabel("F1-score")
    ax.set_title("Per-class F1 (XGBoost, AWID3)")
    ax.grid(axis="y", alpha=0)
    fig.savefig(FIG / "fig_per_class_f1.png", bbox_inches="tight"); plt.close(fig)

    # === Figure 5: model comparison (from benchmark.json) ===
    bench_path = ROOT / "data" / "reports" / "benchmark.json"
    if bench_path.exists():
        res = [r for r in json.loads(bench_path.read_text())["results"]
               if "error" not in r and r.get("f1", 0) > 0]
        res.sort(key=lambda r: r["f1"])
        fig, ax = plt.subplots(figsize=(7, 5))
        cols = [OKABE[2] if r["model"] == res[-1]["model"] else BLUE for r in res]
        ax.barh([r["model"] for r in res], [r["f1"] for r in res], color=cols, height=0.7)
        for i, r in enumerate(res):
            ax.text(r["f1"] + 0.005, i, f"{r['f1']:.3f}", va="center", fontsize=8)
        ax.set_xlim(0, 1.05); ax.set_xlabel("macro-F1")
        ax.set_title("Model comparison — AWID3 (best highlighted)")
        ax.grid(axis="y", alpha=0)
        fig.savefig(FIG / "fig_model_comparison.png", bbox_inches="tight"); plt.close(fig)

    # === Figure 6: feature importance (top 15) ===
    imp = model.feature_importances_
    idx = np.argsort(imp)[::-1][:15][::-1]
    fig, ax = plt.subplots(figsize=(7, 6))
    ax.barh([names[i] for i in idx], imp[idx], color=BLUE, height=0.7)
    ax.set_xlabel("XGBoost importance"); ax.set_title("Top-15 feature importance (AWID3)")
    ax.grid(axis="y", alpha=0)
    fig.savefig(FIG / "fig_feature_importance.png", bbox_inches="tight"); plt.close(fig)

    # === Figure 7: ablation (F1 vs top-k features) ===
    ranked = np.argsort(imp)[::-1]
    ks = [5, 10, 15, 20, 30, len(names)]
    sub = np.random.RandomState(42).choice(len(Xtr), min(25000, len(Xtr)), replace=False)
    f1s = []
    from sklearn.metrics import f1_score
    for k in ks:
        cols = ranked[:k]
        m = train_model(Xtr[np.ix_(sub, cols)], ytr[sub], n=150)
        f1s.append(f1_score(yte, m.predict(Xte[:, cols]), average="macro", zero_division=0))
    fig, ax = plt.subplots(figsize=(7, 5))
    ax.plot(ks, f1s, "-o", color=OKABE[0], lw=2, ms=7)
    for k, f in zip(ks, f1s):
        ax.text(k, f - 0.02, f"{f:.3f}", ha="center", fontsize=8)
    ax.set_xlabel("Number of top features"); ax.set_ylabel("macro-F1")
    ax.set_title("Ablation — F1 vs feature-set size (AWID3)")
    fig.savefig(FIG / "fig_ablation.png", bbox_inches="tight"); plt.close(fig)

    summary = {
        "model": "XGBoost", "classes": len(classes), "test_samples": len(yte),
        "roc_auc_micro": round(auc_mi, 4), "roc_auc_macro": round(float(np.mean(aucs)), 4),
        "macro_f1": round(rep["macro avg"]["f1-score"], 4),
        "accuracy": round(rep["accuracy"], 4),
        "inference_latency_us_per_sample": round(latency_us, 2),
        "throughput_samples_per_s": round(throughput, 0),
        "ablation": {str(k): round(f, 4) for k, f in zip(ks, f1s)},
        "figures": sorted(p.name for p in FIG.glob("*.png")),
    }
    (ROOT / "data" / "reports" / "scientific_benchmark.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8")

    print("\n  Figures written to", FIG)
    for p in summary["figures"]:
        print("   -", p)
    print(f"\n  ROC-AUC micro={summary['roc_auc_micro']} macro={summary['roc_auc_macro']}"
          f" · macro-F1={summary['macro_f1']}")
    print(f"  Inference: {summary['inference_latency_us_per_sample']} us/sample "
          f"({int(summary['throughput_samples_per_s'])} samples/s)")
    print(f"  Ablation F1: {summary['ablation']}")
    print("\nRESULT: PASS - scientific benchmark figures generated"
          if len(summary["figures"]) >= 6 else "\nRESULT: FAIL")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
