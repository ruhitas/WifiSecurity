"""SHAP-based explainer + reasoning-report generator (with LIME fallback)."""
from __future__ import annotations

import numpy as np

try:
    import shap
    _HAS_SHAP = True
except Exception:
    _HAS_SHAP = False


class Explainer:
    def __init__(self, model, feature_names, class_names, background=None):
        self.model = model
        self.feature_names = list(feature_names)
        self.class_names = list(class_names)
        self.backend = "none"
        self._shap = None
        if _HAS_SHAP:
            try:
                self._shap = shap.TreeExplainer(model)
                self.backend = "shap-tree"
            except Exception:
                self._shap = None
        self._background = background

    # -- contributions -----------------------------------------------------
    def _shap_for(self, X):
        sv = self._shap.shap_values(X)
        return sv  # list[n_class] of (n,feat) OR ndarray (n,feat,n_class)

    @staticmethod
    def _pick(sv, i, cidx):
        if isinstance(sv, list):
            return np.asarray(sv[cidx])[i]
        arr = np.asarray(sv)
        if arr.ndim == 3:
            return arr[i, :, cidx]
        return arr[i]

    def _lime_local(self, x, cidx, n=300, seed=0):
        """From-scratch LIME: local linear fit of class prob around x."""
        from sklearn.linear_model import Ridge
        rng = np.random.default_rng(seed)
        scale = np.std(self._background, axis=0) if self._background is not None else np.ones_like(x)
        samples = x + rng.normal(0, 1, size=(n, len(x))) * (scale + 1e-6)
        proba = self.model.predict_proba(samples)[:, cidx]
        w = np.exp(-np.sum(((samples - x) / (scale + 1e-6)) ** 2, axis=1) / 20.0)
        lr = Ridge(alpha=1.0).fit(samples, proba, sample_weight=w)
        return lr.coef_

    # -- public ------------------------------------------------------------
    def reasoning_report(self, x, top_k=5) -> dict:
        x = np.asarray(x, dtype=float)
        proba = self.model.predict_proba(x.reshape(1, -1))[0]
        cidx = int(np.argmax(proba))
        label = self.class_names[cidx]
        confidence = float(proba[cidx])

        if self._shap is not None:
            contrib = self._pick(self._shap_for(x.reshape(1, -1)), 0, cidx)
            method = "SHAP"
        else:
            contrib = self._lime_local(x, cidx)
            method = "LIME"

        order = np.argsort(np.abs(contrib))[::-1][:top_k]
        top = [{"feature": self.feature_names[i],
                "contribution": round(float(contrib[i]), 5),
                "value": round(float(x[i]), 4)} for i in order]

        drivers = ", ".join(f"{t['feature']} ({'+' if t['contribution'] >= 0 else ''}{t['contribution']})"
                            for t in top)
        text = (f"Classified as '{label}' with {confidence:.0%} confidence. "
                f"Main drivers ({method}): {drivers}.")
        return {"label": label, "confidence": round(confidence, 4),
                "method": method, "top_features": top, "explanation": text}

    def global_importance(self, X, top_k=10):
        if self._shap is None:
            imp = getattr(self.model, "feature_importances_", None)
            if imp is None:
                return []
            order = np.argsort(imp)[::-1][:top_k]
            return [(self.feature_names[i], round(float(imp[i]), 5)) for i in order]
        sv = self._shap_for(np.asarray(X))
        if isinstance(sv, list):
            mean_abs = np.mean([np.abs(np.asarray(s)) for s in sv], axis=(0, 1))
        else:
            arr = np.asarray(sv)
            mean_abs = np.abs(arr).mean(axis=(0, 2)) if arr.ndim == 3 else np.abs(arr).mean(0)
        order = np.argsort(mean_abs)[::-1][:top_k]
        return [(self.feature_names[i], round(float(mean_abs[i]), 5)) for i in order]
