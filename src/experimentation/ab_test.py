"""Frequentist A/B testing for binary metrics + BH FDR for multi-test."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import stats


@dataclass
class ABTestResult:
    metric: str
    control_n: int
    treatment_n: int
    control_rate: float
    treatment_rate: float
    absolute_lift: float
    relative_lift: float
    z_stat: float
    p_value: float
    ci95_low: float
    ci95_high: float
    significant: bool


class ABTest:
    """Two-proportion z-test (pooled SE) with Wald 95% CI on the difference."""

    @staticmethod
    def proportion_test(control_success: int, control_total: int,
                        treatment_success: int, treatment_total: int,
                        metric_name: str = "ctr",
                        alpha: float = 0.01) -> ABTestResult:
        if control_total == 0 or treatment_total == 0:
            raise ValueError("Sample sizes must be positive.")

        p1 = control_success / control_total
        p2 = treatment_success / treatment_total
        pooled = (control_success + treatment_success) / (control_total + treatment_total)
        se = np.sqrt(pooled * (1 - pooled) * (1.0 / control_total + 1.0 / treatment_total))
        z = (p2 - p1) / se if se > 0 else 0.0
        p_value = 2 * (1 - stats.norm.cdf(abs(z)))

        # CI uses unpooled SE because under H_A the variances are not equal.
        se_diff = np.sqrt(p1 * (1 - p1) / control_total + p2 * (1 - p2) / treatment_total)
        ci_low = (p2 - p1) - 1.96 * se_diff
        ci_high = (p2 - p1) + 1.96 * se_diff

        rel_lift = (p2 - p1) / p1 if p1 > 0 else 0.0
        return ABTestResult(
            metric=metric_name,
            control_n=control_total,
            treatment_n=treatment_total,
            control_rate=round(p1, 6),
            treatment_rate=round(p2, 6),
            absolute_lift=round(p2 - p1, 6),
            relative_lift=round(rel_lift, 4),
            z_stat=round(float(z), 4),
            p_value=round(float(p_value), 6),
            ci95_low=round(float(ci_low), 6),
            ci95_high=round(float(ci_high), 6),
            significant=bool(p_value < alpha),
        )

    @staticmethod
    def required_sample_size(baseline_rate: float, mde: float, alpha: float = 0.05,
                             power: float = 0.8) -> int:
        """Per-arm N for a two-sided two-proportion test at the given MDE."""
        z_alpha = stats.norm.ppf(1 - alpha / 2)
        z_beta = stats.norm.ppf(power)
        p1 = baseline_rate
        p2 = baseline_rate * (1 + mde)
        p_bar = (p1 + p2) / 2
        numerator = (z_alpha * np.sqrt(2 * p_bar * (1 - p_bar))
                     + z_beta * np.sqrt(p1 * (1 - p1) + p2 * (1 - p2))) ** 2
        denominator = (p2 - p1) ** 2
        return int(np.ceil(numerator / denominator)) if denominator > 0 else 0


class BenjaminiHochberg:
    """BH step-up procedure. Controls FDR under independence + PRDS."""

    @staticmethod
    def correct(p_values: list[float], fdr: float = 0.05) -> list[bool]:
        n = len(p_values)
        if n == 0:
            return []
        order = np.argsort(p_values)
        ranked = np.array(p_values)[order]
        thresholds = (np.arange(1, n + 1) / n) * fdr
        # Step-up: find the largest k with p_(k) <= (k/n) * fdr, reject all
        # hypotheses with rank <= k.
        passing = ranked <= thresholds
        if not passing.any():
            return [False] * n
        k = np.max(np.where(passing)[0])
        rejected = np.zeros(n, dtype=bool)
        rejected[order[: k + 1]] = True
        return rejected.tolist()
