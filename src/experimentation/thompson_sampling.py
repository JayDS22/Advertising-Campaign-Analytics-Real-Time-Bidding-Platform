"""Beta-Bernoulli Thompson Sampling MAB. Used for creative optimization."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class Arm:
    arm_id: str
    alpha: float = 1.0   # successes + 1
    beta: float = 1.0    # failures + 1
    impressions: int = 0
    rewards: int = 0

    def posterior_mean(self) -> float:
        return self.alpha / (self.alpha + self.beta)

    def credible_interval(self, level: float = 0.95) -> tuple[float, float]:
        from scipy import stats
        lo = float(stats.beta.ppf((1 - level) / 2, self.alpha, self.beta))
        hi = float(stats.beta.ppf(1 - (1 - level) / 2, self.alpha, self.beta))
        return lo, hi


@dataclass
class ThompsonSamplingMAB:
    """Bandit selector. One Beta posterior per arm; sample then argmax."""
    arms: dict[str, Arm] = field(default_factory=dict)
    seed: int = 42

    def __post_init__(self):
        self._rng = np.random.default_rng(self.seed)

    def add_arm(self, arm_id: str) -> None:
        self.arms.setdefault(arm_id, Arm(arm_id=arm_id))

    def select_arm(self) -> str:
        if not self.arms:
            raise ValueError("No arms registered.")
        samples = {aid: float(self._rng.beta(a.alpha, a.beta))
                   for aid, a in self.arms.items()}
        return max(samples, key=samples.get)  # type: ignore[arg-type]

    def update(self, arm_id: str, reward: int) -> None:
        a = self.arms[arm_id]
        a.impressions += 1
        a.rewards += int(reward)
        if reward:
            a.alpha += 1
        else:
            a.beta += 1

    def snapshot(self) -> list[dict]:
        out = []
        for aid, a in self.arms.items():
            lo, hi = a.credible_interval()
            out.append({
                "arm_id": aid,
                "impressions": a.impressions,
                "rewards": a.rewards,
                "ctr_mean": round(a.posterior_mean(), 4),
                "ctr_ci_low": round(lo, 4),
                "ctr_ci_high": round(hi, 4),
            })
        out.sort(key=lambda x: x["ctr_mean"], reverse=True)
        return out
