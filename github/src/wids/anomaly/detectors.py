"""Anomaly detectors with a common fit / score interface."""
from __future__ import annotations

import numpy as np
import torch
import torch.nn as nn
from sklearn.ensemble import IsolationForest
from sklearn.svm import OneClassSVM


class IsolationForestAD:
    name = "IsolationForest"

    def __init__(self, seed=42):
        self.m = IsolationForest(n_estimators=200, random_state=seed)

    def fit(self, Xn):
        self.m.fit(Xn); return self

    def score(self, X):
        return -self.m.score_samples(X)   # higher = more anomalous


class OneClassSVMAD:
    name = "OneClassSVM"

    def __init__(self, nu=0.05, gamma="scale"):
        self.m = OneClassSVM(nu=nu, gamma=gamma)

    def fit(self, Xn):
        self.m.fit(Xn); return self

    def score(self, X):
        return -self.m.decision_function(X)


def _mlp(dims, out_act=None):
    layers = []
    for i in range(len(dims) - 1):
        layers.append(nn.Linear(dims[i], dims[i + 1]))
        if i < len(dims) - 2:
            layers.append(nn.ReLU())
    if out_act:
        layers.append(out_act)
    return nn.Sequential(*layers)


def _train(model, Xn, loss_fn, epochs=60, lr=1e-3, batch=64, seed=42):
    torch.manual_seed(seed)
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    Xt = torch.tensor(Xn, dtype=torch.float32)
    n = len(Xt)
    for _ in range(epochs):
        model.train()
        perm = torch.randperm(n)
        for i in range(0, n, batch):
            idx = perm[i:i + batch]
            opt.zero_grad()
            loss = loss_fn(Xt[idx])
            loss.backward()
            opt.step()
    return model


class AutoEncoderAD:
    name = "AutoEncoder"

    def __init__(self, d, seed=42):
        self.enc = _mlp([d, 64, 16]); self.dec = _mlp([16, 64, d]); self.seed = seed

    def _recon(self, X):
        return self.dec(self.enc(X))

    def fit(self, Xn):
        net = nn.ModuleList([self.enc, self.dec])
        mse = nn.MSELoss()
        _train(net, Xn, lambda xb: mse(self._recon(xb), xb), seed=self.seed)
        return self

    def score(self, X):
        self.enc.eval(); self.dec.eval()
        with torch.no_grad():
            Xt = torch.tensor(X, dtype=torch.float32)
            err = ((self._recon(Xt) - Xt) ** 2).mean(1)
        return err.numpy()


class VAE_AD:
    name = "VAE"

    def __init__(self, d, latent=16, seed=42):
        self.enc = _mlp([d, 64, 32]); self.mu = nn.Linear(32, latent)
        self.lv = nn.Linear(32, latent); self.dec = _mlp([latent, 64, d]); self.seed = seed

    def _forward(self, X):
        h = self.enc(X); mu = self.mu(h); lv = self.lv(h)
        z = mu + torch.randn_like(mu) * torch.exp(0.5 * lv)
        return self.dec(z), mu, lv

    def fit(self, Xn):
        net = nn.ModuleList([self.enc, self.mu, self.lv, self.dec])

        def loss_fn(xb):
            rec, mu, lv = self._forward(xb)
            recon = ((rec - xb) ** 2).mean()
            kl = -0.5 * torch.mean(1 + lv - mu.pow(2) - lv.exp())
            return recon + 0.001 * kl
        _train(net, Xn, loss_fn, seed=self.seed)
        return self

    def score(self, X):
        for m in (self.enc, self.mu, self.lv, self.dec):
            m.eval()
        with torch.no_grad():
            Xt = torch.tensor(X, dtype=torch.float32)
            rec, _, _ = self._forward(Xt)
            err = ((rec - Xt) ** 2).mean(1)
        return err.numpy()


class DeepSVDD:
    name = "DeepSVDD"

    def __init__(self, d, latent=16, seed=42):
        self.net = _mlp([d, 64, latent]); self.c = None; self.seed = seed

    def fit(self, Xn):
        torch.manual_seed(self.seed)
        Xt = torch.tensor(Xn, dtype=torch.float32)
        with torch.no_grad():
            self.c = self.net(Xt).mean(0)      # hypersphere center from normal
        _train(self.net, Xn,
               lambda xb: ((self.net(xb) - self.c) ** 2).sum(1).mean(), seed=self.seed)
        return self

    def score(self, X):
        self.net.eval()
        with torch.no_grad():
            z = self.net(torch.tensor(X, dtype=torch.float32))
            return ((z - self.c) ** 2).sum(1).numpy()


def build_detectors(d, seed=42):
    return [IsolationForestAD(seed), OneClassSVMAD(),
            AutoEncoderAD(d, seed), VAE_AD(d, seed=seed), DeepSVDD(d, seed=seed)]
