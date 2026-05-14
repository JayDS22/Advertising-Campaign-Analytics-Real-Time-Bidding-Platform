"""Logistic-regression CTR model over hashed feature indices.
Vowpal-style hashing trick. O(active features) updates, no vocab to maintain.
"""
from __future__ import annotations

import hashlib

import numpy as np


class CTRPredictor:
    """Online LR CTR model.

    Categorical signals (campaign_id, creative_id, geo, device, hour, ...)
    are hashed to a fixed-size weight vector. Memory is constant in the
    cardinality of the input space; collisions are tolerated.
    """

    def __init__(self, n_features: int = 2 ** 18, lr: float = 0.05,
                 l2: float = 1e-6):
        self.n_features = n_features
        self.lr = lr
        self.l2 = l2
        self.w = np.zeros(n_features, dtype=np.float32)
        self.bias = 0.0
        self.n_updates = 0

    def _hash(self, feat: str) -> int:
        h = int(hashlib.md5(feat.encode()).hexdigest()[:8], 16)
        return h % self.n_features

    def _encode(self, features: dict) -> list[int]:
        return [self._hash(f"{k}={v}") for k, v in features.items()]

    @staticmethod
    def _sigmoid(x: float) -> float:
        # Two-branch form to avoid overflow in exp() for large negative x.
        if x >= 0:
            z = np.exp(-x)
            return float(1.0 / (1.0 + z))
        z = np.exp(x)
        return float(z / (1.0 + z))

    def predict_proba(self, features: dict) -> float:
        idx = self._encode(features)
        z = self.bias + float(self.w[idx].sum())
        return self._sigmoid(z)

    def update(self, features: dict, label: int) -> float:
        idx = self._encode(features)
        z = self.bias + float(self.w[idx].sum())
        p = self._sigmoid(z)
        err = p - label
        # Per-feature SGD step with L2 shrinkage.
        for i in idx:
            self.w[i] -= self.lr * (err + self.l2 * self.w[i])
        self.bias -= self.lr * err
        self.n_updates += 1
        return p
