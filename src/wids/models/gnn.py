"""Graph neural network over the station<->BSSID graph (Phase 10, GNN branch).

Builds a per-window bipartite graph from raw 802.11 frames (stations and APs as
nodes, associations as edges, node features from each node's traffic) and
classifies windows with a small from-scratch GCN. This realizes the relational /
GNN novelty highlighted in the literature review and SAD (device/BSSID graph),
without a heavy graph library. Fusing this with HybridNet is the integration step.
"""
from __future__ import annotations

import numpy as np
import torch
import torch.nn as nn

NODE_FEATURES = ["degree", "frame_count", "mean_rssi", "retry_frac",
                 "deauth_frac", "disassoc_frac", "auth_frac", "beacon_frac",
                 "probe_frac", "mgmt_frac", "is_bssid"]

_SUB_FRAC = {"deauth": "deauth", "disassoc": "disassoc", "auth": "auth",
             "beacon": "beacon", "probe_req": "probe"}


def build_window_graph(frames: list[dict]):
    """Return (node_feat [N,F], A_hat [N,N]) for a window of frames."""
    nodes = {}
    def nid(mac):
        if mac not in nodes:
            nodes[mac] = len(nodes)
        return nodes[mac]

    edges = set()
    per_node = {}   # mac -> dict of accumulators
    bssid_set = set()

    def acc(mac):
        return per_node.setdefault(mac, {"frames": 0, "rssi": [], "retry": 0,
                                         "mgmt": 0, "deauth": 0, "disassoc": 0,
                                         "auth": 0, "beacon": 0, "probe": 0})
    for f in frames:
        s, b = f.get("src"), f.get("bssid")
        if not s or not b:
            continue
        nid(s); nid(b)
        bssid_set.add(b)
        edges.add((min(nid(s), nid(b)), max(nid(s), nid(b))))
        a = acc(s)
        a["frames"] += 1
        if f.get("rssi") is not None:
            a["rssi"].append(f["rssi"])
        a["retry"] += 1 if f.get("retry") else 0
        a["mgmt"] += 1 if f.get("type") == "mgmt" else 0
        sk = _SUB_FRAC.get(f.get("subtype"))
        if sk:
            a[sk] += 1

    n = len(nodes)
    if n == 0:
        return None, None
    # adjacency with self-loops
    A = np.eye(n, dtype="float32")
    deg_count = np.zeros(n)
    for i, j in edges:
        A[i, j] = A[j, i] = 1.0
    for i in range(n):
        deg_count[i] = A[i].sum() - 1  # exclude self-loop for the feature
    # symmetric normalization
    d = A.sum(1)
    dinv = 1.0 / np.sqrt(np.maximum(d, 1e-8))
    A_hat = (A * dinv).T * dinv

    # node features
    feat = np.zeros((n, len(NODE_FEATURES)), dtype="float32")
    inv = {v: k for k, v in nodes.items()}
    for i in range(n):
        mac = inv[i]
        a = per_node.get(mac)
        fc = a["frames"] if a else 0
        r = (lambda key: (a[key] / fc if (a and fc) else 0.0))
        feat[i] = [
            deg_count[i],
            fc,
            float(np.mean(a["rssi"])) if (a and a["rssi"]) else 0.0,
            r("retry"), r("deauth"), r("disassoc"), r("auth"),
            r("beacon"), r("probe"), r("mgmt"),
            1.0 if mac in bssid_set else 0.0,
        ]
    return feat, A_hat


class GCN(nn.Module):
    def __init__(self, in_dim: int, hidden: int, n_classes: int):
        super().__init__()
        self.l1 = nn.Linear(in_dim, hidden, bias=False)
        self.l2 = nn.Linear(hidden, hidden, bias=False)
        self.cls = nn.Linear(hidden, n_classes)

    def forward(self, X, A):
        h = torch.relu(A @ self.l1(X))
        h = torch.relu(A @ self.l2(h))
        return self.cls(h.mean(0, keepdim=True))   # graph-level (1, C)
