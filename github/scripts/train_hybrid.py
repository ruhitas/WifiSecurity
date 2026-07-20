"""Phase 10: train the hybrid CNN+Transformer model with XAI."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from wids.models.train import train_hybrid  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DATASETS = ROOT / "data" / "datasets"
REPORTS = ROOT / "data" / "reports"


def latest_dataset():
    csvs = sorted(DATASETS.glob("*.csv"))
    if not csvs:
        raise SystemExit("No dataset. Run scripts/build_dataset.py first.")
    return csvs[-1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=None)
    ap.add_argument("--epochs", type=int, default=60)
    args = ap.parse_args()
    csv_path = Path(args.csv) if args.csv else latest_dataset()

    print(f"== Phase 10 hybrid model (CNN + Transformer + XAI) ==\nDataset: {csv_path}")
    res = train_hybrid(csv_path, epochs=args.epochs)

    print(f"\nFeatures: {res['n_features']} · test samples: {res['n_test']}")
    print(f"Test accuracy: {res['accuracy']}   macro-F1: {res['f1_macro']}")

    print("\n  Per-class F1 (hold-out)")
    print("  " + "-" * 40)
    for cls in res["classes"]:
        print(f"  {cls:<20}{res['report'][cls]['f1-score']:.4f}")
    print("  " + "-" * 40)

    print("\n  XAI — top features per class (input x gradient)")
    print("  " + "-" * 60)
    for i, cls in enumerate(res["classes"]):
        print(f"  {cls:<18}{', '.join(res['xai_top_features'][i][:5])}")
    print("  " + "-" * 60)

    if res["attention_top"]:
        print("\n  Transformer attention — most-attended features")
        print("  " + ", ".join(f for f, _ in res["attention_top"][:8]))

    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "hybrid_model_report.json").write_text(json.dumps({
        "accuracy": res["accuracy"], "f1_macro": res["f1_macro"],
        "classes": res["classes"], "xai_top_features": res["xai_top_features"],
        "attention_top": res["attention_top"],
    }, indent=2), encoding="utf-8")
    print(f"\n  Wrote {REPORTS / 'hybrid_model_report.json'}")

    ok = res["f1_macro"] > 0.8
    print("\nRESULT:", "PASS - hybrid CNN+Transformer trained with XAI"
          if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
