"""Train / evaluate HybridNet with gradient-based XAI."""
from __future__ import annotations

import numpy as np
import torch
import torch.nn as nn
from sklearn.metrics import classification_report, f1_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder, StandardScaler

from ..feature_selection import load_dataset
from ..feature_selection.selectors import drop_low_variance
from .hybrid import HybridNet


def _load(csv_path):
    X, y = load_dataset(csv_path)
    X, _ = drop_low_variance(X)
    return X.values.astype("float32"), y.values, list(X.columns)


def train_hybrid(csv_path, epochs=60, batch_size=64, lr=1e-3, seed=42):
    torch.manual_seed(seed)
    np.random.seed(seed)
    X, y, names = _load(csv_path)
    le = LabelEncoder().fit(y)
    ye = le.transform(y)
    Xtr, Xte, ytr, yte = train_test_split(X, ye, test_size=0.25, stratify=ye, random_state=seed)
    scaler = StandardScaler().fit(Xtr)
    Xtr, Xte = scaler.transform(Xtr).astype("float32"), scaler.transform(Xte).astype("float32")

    Xtr_t = torch.tensor(Xtr); ytr_t = torch.tensor(ytr)
    Xte_t = torch.tensor(Xte); yte_t = torch.tensor(yte)

    model = HybridNet(n_features=X.shape[1], n_classes=len(le.classes_))
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    lossf = nn.CrossEntropyLoss()

    n = len(Xtr_t)
    for ep in range(epochs):
        model.train()
        perm = torch.randperm(n)
        for i in range(0, n, batch_size):
            idx = perm[i:i + batch_size]
            opt.zero_grad()
            loss = lossf(model(Xtr_t[idx]), ytr_t[idx])
            loss.backward()
            opt.step()

    # evaluate
    model.eval()
    with torch.no_grad():
        logits = model(Xte_t)
        pred = logits.argmax(1).numpy()
    acc = float((pred == yte).mean())
    f1 = float(f1_score(yte, pred, average="macro", zero_division=0))
    report = classification_report(yte, pred, target_names=list(le.classes_),
                                   output_dict=True, zero_division=0)

    xai = _saliency(model, Xte_t, len(le.classes_), names)
    attn = model.feature_attention()
    attn_top = None
    if attn is not None:
        order = np.argsort(attn.numpy())[::-1][:10]
        attn_top = [(names[i], round(float(attn[i]), 5)) for i in order]

    return {
        "accuracy": round(acc, 4), "f1_macro": round(f1, 4),
        "classes": list(le.classes_), "report": report,
        "xai_top_features": xai, "attention_top": attn_top,
        "n_features": X.shape[1], "n_test": len(yte),
    }


def _saliency(model, X, n_classes, names, top=6):
    """Input*gradient attribution per class -> top features."""
    X = X.clone().requires_grad_(True)
    logits = model(X)
    out = {}
    for c in range(n_classes):
        g = torch.autograd.grad(logits[:, c].sum(), X, retain_graph=(c < n_classes - 1))[0]
        attr = (g * X).abs().mean(0).detach().numpy()
        order = np.argsort(attr)[::-1][:top]
        out[c] = [names[i] for i in order]
    return out
