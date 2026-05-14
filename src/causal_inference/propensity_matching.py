"""1-to-1 nearest-neighbor matching on logit propensity, caliper-bounded."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.neighbors import NearestNeighbors


@dataclass
class MatchedResult:
    att: float        # ATT estimate (mean of paired diffs)
    se: float
    ci95_low: float
    ci95_high: float
    n_treated: int
    n_matched: int
    overlap_score: float  # mean |logit-PS distance| post-match; lower is better


class PropensityScoreMatcher:
    """Logit-PS, then 1-NN matching with a caliper. Returns ATT + diagnostics."""

    def __init__(self, caliper: float = 0.05, random_state: int = 42):
        self.caliper = caliper
        self.random_state = random_state

    def estimate(self, df: pd.DataFrame, treatment: str, outcome: str,
                 covariates: list[str]) -> MatchedResult:
        if treatment not in df.columns or outcome not in df.columns:
            raise ValueError("treatment and outcome columns must exist")

        X = df[covariates].to_numpy()
        T = df[treatment].astype(int).to_numpy()
        Y = df[outcome].astype(float).to_numpy()

        # P(T=1 | X) from a regularized logit.
        lr = LogisticRegression(max_iter=1000, random_state=self.random_state)
        lr.fit(X, T)
        ps = lr.predict_proba(X)[:, 1]

        # Match on logit(PS) instead of PS itself (Rosenbaum & Rubin 1985).
        eps = 1e-6
        logit_ps = np.log((ps + eps) / (1 - ps + eps))

        treated_idx = np.where(T == 1)[0]
        control_idx = np.where(T == 0)[0]
        if len(control_idx) == 0:
            raise ValueError("no control units")

        nn = NearestNeighbors(n_neighbors=1)
        nn.fit(logit_ps[control_idx].reshape(-1, 1))
        dists, nn_idx = nn.kneighbors(logit_ps[treated_idx].reshape(-1, 1))
        dists = dists.flatten()
        nn_idx = nn_idx.flatten()

        # Drop pairs whose nearest neighbor falls outside the caliper.
        keep = dists <= self.caliper
        matched_treated = treated_idx[keep]
        matched_control = control_idx[nn_idx[keep]]

        if len(matched_treated) == 0:
            return MatchedResult(0.0, 0.0, 0.0, 0.0,
                                 n_treated=len(treated_idx), n_matched=0,
                                 overlap_score=float(dists.mean() if len(dists) else 0))

        treated_outcomes = Y[matched_treated]
        control_outcomes = Y[matched_control]
        diffs = treated_outcomes - control_outcomes
        att = float(diffs.mean())
        se = float(diffs.std(ddof=1) / np.sqrt(len(diffs))) if len(diffs) > 1 else 0.0
        ci_low = att - 1.96 * se
        ci_high = att + 1.96 * se

        return MatchedResult(
            att=round(att, 6),
            se=round(se, 6),
            ci95_low=round(ci_low, 6),
            ci95_high=round(ci_high, 6),
            n_treated=len(treated_idx),
            n_matched=len(matched_treated),
            overlap_score=round(float(dists[keep].mean()), 6) if keep.any() else 0.0,
        )
