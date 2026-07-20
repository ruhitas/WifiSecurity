"""Phase 10 (GNN branch): classify windows from the station<->BSSID graph.

Builds a per-window bipartite graph from raw 802.11 frames and trains a small
from-scratch GCN to classify the window — demonstrating relational/graph-based
detection on graph-structured data (the GNN novelty).
"""
import sys
from itertools import islice
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np  # noqa: E402
import torch  # noqa: E402
import torch.nn as nn  # noqa: E402
from sklearn.metrics import f1_score  # noqa: E402
from sklearn.model_selection import train_test_split  # noqa: E402

from wids.sensors.frames import SyntheticFrameSource  # noqa: E402
from wids.models.gnn import GCN, build_window_graph, NODE_FEATURES  # noqa: E402

CLASSES = ["normal", "deauth_flood", "disassoc_flood", "auth_flood",
           "probe_flood", "beacon_flood"]
WINDOWS_PER_CLASS = 60
WINDOW = 80


def make_graphs():
    graphs, labels = [], []
    for ci, cls in enumerate(CLASSES):
        attack = None if cls == "normal" else cls
        for i in range(WINDOWS_PER_CLASS):
            src = SyntheticFrameSource(channel=6, seed=1000 * ci + i, attack=attack)
            frames = list(islice(src.iterate(), WINDOW))
            feat, A = build_window_graph(frames)
            if feat is None:
                continue
            graphs.append((torch.tensor(feat), torch.tensor(A)))
            labels.append(ci)
    return graphs, np.array(labels)


def main() -> int:
    print("== Phase 10 GNN demo (station<->BSSID graph) ==")
    graphs, labels = make_graphs()
    print(f"Built {len(graphs)} window graphs · node features: {len(NODE_FEATURES)} · classes: {len(CLASSES)}")

    idx = np.arange(len(graphs))
    tr, te = train_test_split(idx, test_size=0.25, stratify=labels, random_state=42)

    torch.manual_seed(42)
    model = GCN(in_dim=len(NODE_FEATURES), hidden=32, n_classes=len(CLASSES))
    opt = torch.optim.Adam(model.parameters(), lr=0.01)
    lossf = nn.CrossEntropyLoss()

    print("Training GCN...")
    for ep in range(40):
        model.train()
        np.random.shuffle(tr)
        opt.zero_grad()
        loss_acc = 0.0
        for k, gi in enumerate(tr, 1):
            X, A = graphs[gi]
            logit = model(X, A)
            loss = lossf(logit, torch.tensor([labels[gi]]))
            loss.backward()
            loss_acc += float(loss)
            if k % 16 == 0:
                opt.step(); opt.zero_grad()
        opt.step()

    # evaluate
    model.eval()
    preds = []
    with torch.no_grad():
        for gi in te:
            X, A = graphs[gi]
            preds.append(int(model(X, A).argmax(1)))
    ytrue = labels[te]
    acc = float((np.array(preds) == ytrue).mean())
    f1 = float(f1_score(ytrue, preds, average="macro", zero_division=0))

    print(f"\n  GNN test accuracy: {acc:.4f}   macro-F1: {f1:.4f}   (n_test={len(te)})")
    ok = acc > 0.6
    print("\nRESULT:", "PASS - GNN classifies windows from graph structure"
          if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
