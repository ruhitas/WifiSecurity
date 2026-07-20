"""Benchmark suite: models, cross-validated metrics, latency, confusion matrix."""
from __future__ import annotations

import numpy as np
from sklearn.ensemble import (ExtraTreesClassifier, GradientBoostingClassifier,
                              RandomForestClassifier)
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (classification_report, confusion_matrix, f1_score,
                             make_scorer, precision_score, recall_score)
from sklearn.model_selection import StratifiedKFold, cross_validate, train_test_split
from sklearn.neighbors import KNeighborsClassifier
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.svm import SVC
from sklearn.tree import DecisionTreeClassifier

SCORING = {
    "accuracy": "accuracy",
    # zero_division=0 keeps the (identical) value but silences the noisy
    # UndefinedMetricWarning for rare classes absent from a CV fold.
    "precision": make_scorer(precision_score, average="macro", zero_division=0),
    "recall": make_scorer(recall_score, average="macro", zero_division=0),
    "f1": make_scorer(f1_score, average="macro", zero_division=0),
    "roc_auc": "roc_auc_ovr_weighted",
}


def build_models(seed: int = 42) -> dict:
    """name -> (estimator, needs_scaling)."""
    models = {
        "LogisticRegression": (LogisticRegression(max_iter=2000), True),
        "KNN": (KNeighborsClassifier(n_neighbors=5), True),
        "SVM_RBF": (SVC(probability=True, random_state=seed), True),
        "DecisionTree": (DecisionTreeClassifier(random_state=seed), False),
        "RandomForest": (RandomForestClassifier(n_estimators=300, random_state=seed, n_jobs=-1), False),
        "ExtraTrees": (ExtraTreesClassifier(n_estimators=300, random_state=seed, n_jobs=-1), False),
        "GradientBoosting": (GradientBoostingClassifier(random_state=seed), False),
        "MLP": (MLPClassifier(hidden_layer_sizes=(128, 64), max_iter=400, random_state=seed), True),
    }
    try:
        from xgboost import XGBClassifier
        models["XGBoost"] = (XGBClassifier(n_estimators=300, tree_method="hist",
                                           eval_metric="mlogloss", random_state=seed), False)
    except Exception:
        pass
    try:
        from lightgbm import LGBMClassifier
        models["LightGBM"] = (LGBMClassifier(n_estimators=300, num_leaves=64,
                                             min_child_samples=5, class_weight="balanced",
                                             random_state=seed, verbose=-1), False)
    except Exception:
        pass
    return models


def _pipe(estimator, needs_scaling):
    if needs_scaling:
        return Pipeline([("scaler", StandardScaler()), ("clf", estimator)])
    return estimator


# fast, scalable models (tree/boosting) for very large datasets
FAST_MODELS = ["DecisionTree", "RandomForest", "ExtraTrees", "XGBoost", "LightGBM"]


def benchmark(X, y, cv: int = 5, seed: int = 42, include=None) -> list[dict]:
    ye = LabelEncoder().fit_transform(y)
    Xv = np.asarray(X)
    skf = StratifiedKFold(n_splits=cv, shuffle=True, random_state=seed)
    n_test = len(ye) / cv
    results = []
    models = build_models(seed)
    if include:
        models = {n: v for n, v in models.items() if n in set(include)}
    for name, (est, scale) in models.items():
        if name == "SVM_RBF" and len(ye) > 20000:
            results.append({"model": name, "error": "skipped (RBF SVM too slow at this scale)",
                            "accuracy": 0, "f1": 0, "roc_auc": 0, "precision": 0,
                            "recall": 0, "fit_time_s": 0, "latency_us": 0})
            continue
        try:
            cvres = cross_validate(_pipe(est, scale), Xv, ye, cv=skf, scoring=SCORING,
                                   return_train_score=False, n_jobs=-1)
            row = {"model": name}
            for key in SCORING:
                row[key] = round(float(np.mean(cvres[f"test_{key}"])), 4)
                row[f"{key}_std"] = round(float(np.std(cvres[f"test_{key}"])), 4)
            row["fit_time_s"] = round(float(np.mean(cvres["fit_time"])), 3)
            # per-sample inference latency (predict/proba over the fold test set)
            row["latency_us"] = round(float(np.mean(cvres["score_time"]) / n_test * 1e6), 1)
            results.append(row)
        except Exception as e:  # keep going if one model fails
            results.append({"model": name, "error": str(e)[:120],
                            "accuracy": 0, "f1": 0, "roc_auc": 0,
                            "precision": 0, "recall": 0, "fit_time_s": 0, "latency_us": 0})
    results.sort(key=lambda r: r.get("f1", 0), reverse=True)
    return results


def confusion_for_best(X, y, best_model_name, seed: int = 42):
    est, scale = build_models(seed)[best_model_name]
    le = LabelEncoder().fit(y)
    ye = le.transform(y)
    Xtr, Xte, ytr, yte = train_test_split(np.asarray(X), ye, test_size=0.25,
                                          stratify=ye, random_state=seed)
    model = _pipe(est, scale)
    model.fit(Xtr, ytr)
    pred = model.predict(Xte)
    cm = confusion_matrix(yte, pred)
    report = classification_report(yte, pred, target_names=list(le.classes_),
                                   output_dict=True, zero_division=0)
    return cm.tolist(), list(le.classes_), report
