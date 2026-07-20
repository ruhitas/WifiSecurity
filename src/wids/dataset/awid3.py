"""Load the real AWID3 CSV dataset into the platform's standard format.

The AWID3_5csv corpus stores per-category CSVs (deauth, disas, krack, kr00k,
rogue_ap, evil_twin, ...). Column ordering differs between categories, so the
'Label' column and features are resolved by NAME, not index. Identifier / time
columns are dropped to avoid leakage (a model must learn from protocol/radio
features, not capture timestamps or specific MAC addresses). Output is a
standard label + numeric-feature CSV consumable by Phases 8-12.
"""
from __future__ import annotations

import glob
import os
from collections import Counter, defaultdict

import numpy as np
import pandas as pd

# exact identifier columns (MAC / IP addresses) that leak the specific devices
_ADDR = {
    "wlan.ra", "wlan.ta", "wlan.sa", "wlan.da", "wlan.bssid", "wlan.addr",
    "wlan.staa", "ip.src", "ip.dst", "ip.addr", "eth.src", "eth.dst",
    "arp.src.hw_mac", "arp.dst.hw_mac", "frame.number",
}
# per-frame / transport sequence counters (encode capture order, not attack type)
_SEQ = {"wlan.seq", "tcp.seq", "tcp.seq_raw", "tcp.ack", "tcp.ack_raw"}


def is_leaky(col: str) -> bool:
    """True for columns that leak the capture/session (time, tsf, addresses,
    sequence counters) rather than describing the attack. Ports are kept."""
    cl = col.lower()
    if "time" in cl or "tsf" in cl or "mactime" in cl or "present.tsft" in cl:
        return True
    if col in _ADDR or col in _SEQ:
        return True
    if cl.endswith((".ra", ".ta", ".sa", ".da", ".bssid")):
        return True
    if ".seq" in cl or cl.endswith(".ack") or cl.endswith(".ack_raw"):
        return True
    return False


def leakage_controlled_features(columns: list[str]) -> list[str]:
    """Return sorted behavioural feature names after applying the leakage policy."""
    return sorted(c for c in columns if c not in ("label", "source") and not is_leaky(c))


def build_awid3_dataset(root: str, out_csv: str, normal_cap: int = 20000,
                        attack_cap: int = 8000, seed: int = 42,
                        files_per_category: int | None = None) -> dict:
    all_files = sorted(glob.glob(os.path.join(root, "**", "*.csv"), recursive=True))
    if not all_files:
        raise SystemExit(f"No CSVs under {root}")

    # group files by top-level category (segment just under root)
    by_cat: dict[str, list[str]] = defaultdict(list)
    rootn = os.path.normpath(root)
    for fp in all_files:
        rel = os.path.relpath(fp, rootn).replace("\\", "/")
        by_cat[rel.split("/")[0]].append(fp)

    counts: Counter = Counter()
    chunks: list[pd.DataFrame] = []
    feature_union: set[str] = set()
    max_scan = files_per_category or 10_000  # safety cap on files read per category

    # Scan each category until its attacks reach the cap (attacks are sparse and
    # scattered across files, so we can't just take the first N files).
    for cat, lst in by_cat.items():
        cat_attack = 0
        for fp in sorted(lst)[:max_scan]:
            if cat_attack >= attack_cap:
                break
            try:
                df = pd.read_csv(fp, low_memory=False)
            except Exception:
                continue
            if "Label" not in df.columns:
                continue
            y = df["Label"].astype(str).str.strip()
            feats = df.drop(columns=["Label"])
            feats = feats.drop(columns=[c for c in feats.columns if is_leaky(c)], errors="ignore")
            feats = feats.apply(pd.to_numeric, errors="coerce")
            feats["label"] = y.values
            feature_union.update(c for c in feats.columns if c != "label")

            for lbl, grp in feats.groupby("label"):
                is_norm = lbl.lower() == "normal"
                cap = normal_cap if is_norm else attack_cap
                remaining = cap - counts[lbl]
                if remaining <= 0:
                    continue
                take = grp.sample(min(len(grp), remaining), random_state=seed) if len(grp) > remaining else grp
                chunks.append(take)
                counts[lbl] += len(take)
                if not is_norm:
                    cat_attack += len(take)

    data = pd.concat(chunks, axis=0, ignore_index=True)
    # align to the full feature union, fill missing/NaN
    feat_cols = sorted(feature_union)
    for c in feat_cols:
        if c not in data.columns:
            data[c] = 0.0
    data[feat_cols] = data[feat_cols].fillna(0.0)
    # drop constant (all-zero) feature columns
    keep = [c for c in feat_cols if data[c].std() > 0]
    out = data[["label"] + keep].copy()
    out["source"] = "awid3"

    os.makedirs(os.path.dirname(out_csv), exist_ok=True)
    out.to_csv(out_csv, index=False)
    return {
        "rows": len(out), "features": len(keep), "classes": dict(Counter(out["label"])),
        "dropped_constant": len(feat_cols) - len(keep), "csv": out_csv,
    }
