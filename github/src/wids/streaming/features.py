"""Windowed feature computation (Phase 6: 300+ features).

Computes a large, extensible feature vector from a window of 802.11 frames,
across the SAD section 8.4 categories:

  * frame / type / subtype counts and rates
  * rich descriptive statistics (22 each) over 12 numeric quantities
    (RSSI, length, inter-frame timing, per-entity distributions, degrees, ...)
  * temporal / inter-frame timing and beacon-interval dynamics
  * entropy of several distributions
  * vendor / OUI fingerprinting (from MAC OUI)
  * graph / relational features over the station<->BSSID bipartite graph (GNN)

Same interface as before (`compute_features(frames) -> dict`), and it preserves
the keys the Phase 5 inference stub relies on (deauth_count, deauth_rate,
disassoc_count, retry_rate, frame_count). Phases 9-10 consume the full vector
with the hybrid ensemble; the GNN uses the graph.* features in particular.
"""
from __future__ import annotations

import math
from collections import Counter, defaultdict

FEATURE_SET_VERSION = "phase6-v2-300plus"

SUBTYPE_NAMES = [
    "beacon", "probe_req", "probe_resp", "auth", "assoc_req", "assoc_resp",
    "deauth", "disassoc", "rts", "cts", "ack", "qos_data", "null", "data",
]

STAT_NAMES = [
    "n", "sum", "mean", "std", "var", "min", "max", "range", "median",
    "p05", "p10", "p25", "p75", "p90", "p95", "iqr", "mad", "cv",
    "skew", "kurtosis", "nonzero_rate", "zero_rate",
]

# quantities that get full numeric_stats treatment (22 features each)
STAT_QUANTITIES = [
    "rssi", "length", "ifd", "src_count", "dst_count", "bssid_count",
    "beacon_interval", "seq_gap", "src_rssi_mean", "pair_count",
    "src_degree", "bssid_degree",
]


def _percentile(s: list[float], q: float) -> float:
    if not s:
        return 0.0
    if len(s) == 1:
        return float(s[0])
    idx = (len(s) - 1) * q
    lo, hi = math.floor(idx), math.ceil(idx)
    if lo == hi:
        return float(s[lo])
    return s[lo] * (hi - idx) + s[hi] * (idx - lo)


def numeric_stats(prefix: str, values) -> dict:
    vals = [float(v) for v in values if v is not None]
    def k(s): return f"{prefix}_{s}"
    n = len(vals)
    if n == 0:
        return {k(s): 0.0 for s in STAT_NAMES}
    s = sorted(vals)
    total = sum(vals)
    mean = total / n
    var = sum((x - mean) ** 2 for x in vals) / n
    std = math.sqrt(var)
    med = _percentile(s, 0.5)
    mad = _percentile(sorted(abs(x - med) for x in vals), 0.5)
    p05, p10, p25, p75, p90, p95 = (_percentile(s, q) for q in (.05, .10, .25, .75, .90, .95))
    cv = std / mean if mean else 0.0
    if std > 0:
        skew = sum(((x - mean) / std) ** 3 for x in vals) / n
        kurt = sum(((x - mean) / std) ** 4 for x in vals) / n
    else:
        skew = kurt = 0.0
    nonzero = sum(1 for x in vals if x != 0)
    return {
        k("n"): n, k("sum"): total, k("mean"): mean, k("std"): std, k("var"): var,
        k("min"): s[0], k("max"): s[-1], k("range"): s[-1] - s[0], k("median"): med,
        k("p05"): p05, k("p10"): p10, k("p25"): p25, k("p75"): p75, k("p90"): p90, k("p95"): p95,
        k("iqr"): p75 - p25, k("mad"): mad, k("cv"): cv, k("skew"): skew, k("kurtosis"): kurt,
        k("nonzero_rate"): nonzero / n, k("zero_rate"): 1 - nonzero / n,
    }


def _entropy(counts) -> float:
    total = sum(counts)
    if total <= 0:
        return 0.0
    return -sum((c / total) * math.log2(c / total) for c in counts if c > 0)


def _gini(counts) -> float:
    vals = sorted(counts)
    n = len(vals)
    s = sum(vals)
    if n == 0 or s == 0:
        return 0.0
    cum = sum(i * x for i, x in enumerate(vals, 1))
    return (2 * cum) / (n * s) - (n + 1) / n


def _oui(mac):
    if not mac or not isinstance(mac, str) or len(mac) < 8:
        return None
    return mac[:8].lower()


def compute_features(frames: list[dict]) -> dict:
    n = len(frames)
    d: dict = {"feature_set_ver": FEATURE_SET_VERSION, "frame_count": n}
    if n == 0:
        # zero-fill so the vector shape is stable
        for q in STAT_QUANTITIES:
            d.update(numeric_stats(q, []))
        return d

    types = Counter(f.get("type") for f in frames)
    subs = Counter(f.get("subtype") for f in frames)

    # -- type counts / rates ------------------------------------------------
    for t in ("mgmt", "ctrl", "data"):
        d[f"{t}_count"] = types.get(t, 0)
        d[f"{t}_rate"] = types.get(t, 0) / n

    # -- subtype counts / rates --------------------------------------------
    for st in SUBTYPE_NAMES:
        d[f"sub_{st}_count"] = subs.get(st, 0)
        d[f"sub_{st}_rate"] = subs.get(st, 0) / n

    # -- composite / attack-indicative (keys used by the inference stub) ----
    deauth = subs.get("deauth", 0)
    disassoc = subs.get("disassoc", 0)
    retries = sum(1 for f in frames if f.get("retry"))
    d["deauth_count"] = deauth
    d["deauth_rate"] = deauth / n
    d["disassoc_count"] = disassoc
    d["disassoc_rate"] = disassoc / n
    d["deauth_disassoc_rate"] = (deauth + disassoc) / n
    d["auth_rate"] = subs.get("auth", 0) / n
    d["assoc_rate"] = subs.get("assoc_req", 0) / n
    d["probe_req_rate"] = subs.get("probe_req", 0) / n
    d["probe_resp_rate"] = subs.get("probe_resp", 0) / n
    d["retry_count"] = retries
    d["retry_rate"] = retries / n

    # -- entities & broadcast ----------------------------------------------
    srcs = Counter(f.get("src") for f in frames)
    dsts = Counter(f.get("dst") for f in frames)
    bssids = Counter(f.get("bssid") for f in frames)
    pairs = Counter((f.get("src"), f.get("bssid")) for f in frames)
    bcast = sum(1 for f in frames if f.get("dst") == "ff:ff:ff:ff:ff:ff")
    d["unique_src"] = len(srcs)
    d["unique_dst"] = len(dsts)
    d["unique_bssid"] = len(bssids)
    d["unique_pairs"] = len(pairs)
    d["broadcast_count"] = bcast
    d["broadcast_rate"] = bcast / n

    # -- entropy ------------------------------------------------------------
    lengths = [f.get("length", 0) or 0 for f in frames]
    rssis = [f["rssi"] for f in frames if f.get("rssi") is not None]
    len_buckets = Counter(min(int((l or 0) // 128), 11) for l in lengths)
    rssi_buckets = Counter(min(int((r + 100) // 10), 9) for r in rssis)
    d["subtype_entropy"] = _entropy(list(subs.values()))
    d["type_entropy"] = _entropy(list(types.values()))
    d["src_entropy"] = _entropy(list(srcs.values()))
    d["dst_entropy"] = _entropy(list(dsts.values()))
    d["bssid_entropy"] = _entropy(list(bssids.values()))
    d["length_bucket_entropy"] = _entropy(list(len_buckets.values()))
    d["rssi_bucket_entropy"] = _entropy(list(rssi_buckets.values()))

    # -- vendor / OUI -------------------------------------------------------
    ouis = Counter(o for o in (_oui(f.get("src")) for f in frames) if o)
    d["unique_oui"] = len(ouis)
    d["top_oui_share"] = (max(ouis.values()) / n) if ouis else 0.0
    d["oui_entropy"] = _entropy(list(ouis.values()))
    d["oui_gini"] = _gini(list(ouis.values()))

    # -- channel ------------------------------------------------------------
    chans = Counter(f.get("channel") for f in frames if f.get("channel") is not None)
    d["channel"] = frames[-1].get("channel") or 0
    d["channel_changes"] = max(0, len(chans) - 1)

    # -- ratios -------------------------------------------------------------
    d["data_mgmt_ratio"] = types.get("data", 0) / max(1, types.get("mgmt", 0))
    d["mgmt_total_ratio"] = types.get("mgmt", 0) / n
    d["ctrl_total_ratio"] = types.get("ctrl", 0) / n

    # -- temporal -----------------------------------------------------------
    ts = sorted(f.get("ts", 0.0) for f in frames)
    ifd = [b - a for a, b in zip(ts, ts[1:])]
    span = (ts[-1] - ts[0]) if len(ts) > 1 else 0.0
    d["window_span_s"] = span
    d["frames_per_sec"] = (n / span) if span > 0 else 0.0

    # beacon intervals per bssid
    beacon_ts = defaultdict(list)
    for f in frames:
        if f.get("subtype") == "beacon":
            beacon_ts[f.get("bssid")].append(f.get("ts", 0.0))
    beacon_intervals = []
    for lst in beacon_ts.values():
        lst.sort()
        beacon_intervals.extend(b - a for a, b in zip(lst, lst[1:]))

    # sequence gaps per src
    seq_by_src = defaultdict(list)
    for f in frames:
        if f.get("seq") is not None:
            seq_by_src[f.get("src")].append(f.get("seq"))
    seq_gaps = []
    for lst in seq_by_src.values():
        lst.sort()
        seq_gaps.extend(max(0, (b - a) - 1) for a, b in zip(lst, lst[1:]))

    # -- graph (station <-> BSSID bipartite) --------------------------------
    src_to_bssids = defaultdict(set)
    bssid_to_srcs = defaultdict(set)
    for f in frames:
        s_, b_ = f.get("src"), f.get("bssid")
        if s_ and b_:
            src_to_bssids[s_].add(b_)
            bssid_to_srcs[b_].add(s_)
    src_deg = [len(v) for v in src_to_bssids.values()]
    bssid_deg = [len(v) for v in bssid_to_srcs.values()]
    edges = len(pairs)
    ns, nb = len(src_to_bssids), len(bssid_to_srcs)
    mobile = sum(1 for v in src_to_bssids.values() if len(v) > 1)  # MAC roaming
    d["graph_src_nodes"] = ns
    d["graph_bssid_nodes"] = nb
    d["graph_edges"] = edges
    d["graph_density"] = edges / (ns * nb) if ns and nb else 0.0
    d["graph_mobile_src"] = mobile
    d["graph_mobility_rate"] = mobile / ns if ns else 0.0
    d["graph_max_bssid_fanout"] = max(bssid_deg) if bssid_deg else 0
    d["graph_avg_src_degree"] = (sum(src_deg) / ns) if ns else 0.0
    d["graph_avg_bssid_degree"] = (sum(bssid_deg) / nb) if nb else 0.0

    # per-entity mean rssi distribution
    src_rssi = defaultdict(list)
    for f in frames:
        if f.get("rssi") is not None:
            src_rssi[f.get("src")].append(f["rssi"])
    src_rssi_means = [sum(v) / len(v) for v in src_rssi.values() if v]

    # -- rich numeric statistics (22 each) ----------------------------------
    d.update(numeric_stats("rssi", rssis))
    d.update(numeric_stats("length", lengths))
    d.update(numeric_stats("ifd", ifd))
    d.update(numeric_stats("src_count", list(srcs.values())))
    d.update(numeric_stats("dst_count", list(dsts.values())))
    d.update(numeric_stats("bssid_count", list(bssids.values())))
    d.update(numeric_stats("beacon_interval", beacon_intervals))
    d.update(numeric_stats("seq_gap", seq_gaps))
    d.update(numeric_stats("src_rssi_mean", src_rssi_means))
    d.update(numeric_stats("pair_count", list(pairs.values())))
    d.update(numeric_stats("src_degree", src_deg))
    d.update(numeric_stats("bssid_degree", bssid_deg))

    # round floats to keep the message compact
    for key, val in d.items():
        if isinstance(val, float):
            d[key] = round(val, 5)
    return d


def feature_names(sample_window: list[dict] | None = None) -> list[str]:
    """Return the sorted feature names produced by compute_features."""
    sample = sample_window or [{
        "type": "mgmt", "subtype": "beacon", "src": "00:11:22:33:44:55",
        "dst": "ff:ff:ff:ff:ff:ff", "bssid": "00:11:22:33:44:55",
        "rssi": -50, "length": 200, "retry": False, "seq": 1, "ts": 0.0, "channel": 6,
    }]
    return sorted(k for k in compute_features(sample) if k != "feature_set_ver")
