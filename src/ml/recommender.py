"""Matrix-factorization recommender, SGD-trained.

Implicit-feedback factorization on (user, creative) interactions. Used
by the bidder for CTR ranking and by the dashboard for top-K ad recs.
NDCG@k is here so train/eval can share the same scoring code.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


def ndcg_at_k(predicted_ranking: list[str], relevances: dict[str, float], k: int = 10) -> float:
    """NDCG@k. ``relevances`` is the ground-truth grade per item id."""
    if not predicted_ranking or k <= 0:
        return 0.0
    dcg = 0.0
    for i, item in enumerate(predicted_ranking[:k]):
        rel = relevances.get(item, 0.0)
        dcg += (2 ** rel - 1) / math.log2(i + 2)
    ideal = sorted(relevances.values(), reverse=True)[:k]
    idcg = sum((2 ** r - 1) / math.log2(i + 2) for i, r in enumerate(ideal))
    return dcg / idcg if idcg > 0 else 0.0


@dataclass
class CollaborativeFilteringRecommender:
    """Low-rank MF model. SGD with L2 regularization."""

    n_factors: int = 32
    n_iters: int = 15
    reg: float = 0.05
    lr: float = 0.05

    def __post_init__(self):
        self.user_factors: dict[str, np.ndarray] = {}
        self.item_factors: dict[str, np.ndarray] = {}
        self._rng = np.random.default_rng(42)

    def _init_factor(self) -> np.ndarray:
        return self._rng.standard_normal(self.n_factors) * 0.05

    def fit(self, interactions: list[tuple[str, str, float]]) -> dict:
        users = {u for u, _, _ in interactions}
        items = {i for _, i, _ in interactions}
        for u in users:
            self.user_factors.setdefault(u, self._init_factor())
        for i in items:
            self.item_factors.setdefault(i, self._init_factor())

        history = []
        for epoch in range(self.n_iters):
            self._rng.shuffle(interactions)  # type: ignore[arg-type]
            sse = 0.0
            for u, i, r in interactions:
                p = self.user_factors[u]
                q = self.item_factors[i]
                pred = float(p @ q)
                err = r - pred
                sse += err * err
                self.user_factors[u] = p + self.lr * (err * q - self.reg * p)
                self.item_factors[i] = q + self.lr * (err * p - self.reg * q)
            history.append(sse / max(1, len(interactions)))
        return {"epochs": self.n_iters, "final_mse": history[-1] if history else 0.0,
                "n_users": len(users), "n_items": len(items)}

    def recommend(self, user_id: str, k: int = 10,
                  exclude: set[str] | None = None) -> list[tuple[str, float]]:
        if user_id not in self.user_factors or not self.item_factors:
            return []
        p = self.user_factors[user_id]
        scores: list[tuple[str, float]] = []
        for item, q in self.item_factors.items():
            if exclude and item in exclude:
                continue
            scores.append((item, float(p @ q)))
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:k]
