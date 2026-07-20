"""Feature-selection methods and consensus ranking."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_selection import (RFE, VarianceThreshold, f_classif,
                                       mutual_info_classif)
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.decomposition import PCA

META_COLS = ["label", "source", "window_index", "feature_set_ver"]


def load_dataset(csv_path):
    df = pd.read_csv(csv_path)
    y = df["label"].astype(str)
    X = df.drop(columns=[c for c in META_COLS if c in df.columns])
    X = X.select_dtypes(include=[np.number]).fillna(0.0)
    return X, y


def drop_low_variance(X):
    vt = VarianceThreshold(0.0)
    vt.fit(X)
    keep = X.columns[vt.get_support()]
    dropped = [c for c in X.columns if c not in set(keep)]
    return X[keep], dropped


def _scores(names, values):
    values = np.nan_to_num(np.asarray(values, dtype=float))
    return {n: float(v) for n, v in zip(names, values)}


def run_all_methods(X, y, rf_estimators=200, rfe_keep=30, perm_repeats=5, seed=42):
    """Return {method: {feature: score(higher=better)}} plus a fitted RF."""
    cols = list(X.columns)
    Xv = X.values
    ye = LabelEncoder().fit_transform(y)
    results = {}

    # 1. Mutual information
    results["mutual_info"] = _scores(cols, mutual_info_classif(Xv, ye, random_state=seed))

    # 2. ANOVA F-test
    f, _ = f_classif(Xv, ye)
    results["anova_f"] = _scores(cols, f)

    # 3. Random-forest impurity importance
    rf = RandomForestClassifier(n_estimators=rf_estimators, random_state=seed, n_jobs=-1)
    rf.fit(Xv, ye)
    results["rf_importance"] = _scores(cols, rf.feature_importances_)

    # 4. Permutation importance (on the fitted RF)
    perm = permutation_importance(rf, Xv, ye, n_repeats=perm_repeats,
                                  random_state=seed, n_jobs=-1)
    results["permutation"] = _scores(cols, perm.importances_mean)

    # 5. L1 / LASSO (multinomial logistic, standardized)
    Xs = StandardScaler().fit_transform(Xv)
    l1 = LogisticRegression(solver="saga", l1_ratio=1.0, C=0.1, max_iter=6000)
    l1.fit(Xs, ye)
    coef = np.abs(l1.coef_).mean(axis=0)  # mean |coef| across classes
    results["lasso_l1"] = _scores(cols, coef)

    # 6. RFE (recursive elimination with a random forest)
    rfe = RFE(RandomForestClassifier(n_estimators=100, random_state=seed, n_jobs=-1),
              n_features_to_select=rfe_keep, step=10)
    rfe.fit(Xv, ye)
    # lower ranking_ is better (1 = selected); convert to higher=better score
    rfe_score = (rfe.ranking_.max() - rfe.ranking_ + 1).astype(float)
    results["rfe"] = _scores(cols, rfe_score)

    return results


def rank_of(scores: dict) -> dict:
    """feature -> rank (1 = best)."""
    order = sorted(scores, key=lambda f: scores[f], reverse=True)
    return {f: i + 1 for i, f in enumerate(order)}


def consensus_ranking(results: dict, top_k_votes: int = 30):
    """Combine methods: average rank + vote count in each method's top-K."""
    methods = list(results)
    ranks = {m: rank_of(results[m]) for m in methods}
    features = list(next(iter(results.values())).keys())
    rows = []
    for f in features:
        avg_rank = float(np.mean([ranks[m][f] for m in methods]))
        votes = sum(1 for m in methods if ranks[m][f] <= top_k_votes)
        rows.append({"feature": f, "avg_rank": round(avg_rank, 2), "votes": votes})
    rows.sort(key=lambda r: (r["avg_rank"], -r["votes"]))
    return rows


def pca_components_for_variance(X, variance=0.95):
    Xs = StandardScaler().fit_transform(X.values)
    pca = PCA().fit(Xs)
    cum = np.cumsum(pca.explained_variance_ratio_)
    n = int(np.searchsorted(cum, variance) + 1)
    return n, float(cum[min(n - 1, len(cum) - 1)])
