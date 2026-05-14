import numpy as np
import pandas as pd

from src.causal_inference.did import DifferenceInDifferences
from src.causal_inference.propensity_matching import PropensityScoreMatcher


def _make_did_panel(true_effect=0.2, n_units=200, pre=6, post=6, seed=11):
    rng = np.random.default_rng(seed)
    rows = []
    for u in range(n_units):
        treated = int(u < n_units // 2)
        baseline = rng.normal(10, 2)
        for t in range(-pre, post):
            post_flag = int(t >= 0)
            y = baseline + 0.05 * t + true_effect * treated * post_flag + rng.normal()
            rows.append({"unit_id": u, "time": t, "treated": treated,
                         "post": post_flag, "outcome": y})
    return pd.DataFrame(rows)


def test_did_recovers_known_effect():
    df = _make_did_panel(true_effect=0.5)
    res = DifferenceInDifferences().fit(df)
    assert abs(res.treatment_effect - 0.5) < 0.2
    assert res.p_value < 0.05


def test_propensity_matching_recovers_effect():
    rng = np.random.default_rng(42)
    n = 1500
    age = rng.normal(35, 10, n)
    income = rng.normal(60000, 20000, n)
    eng = rng.beta(2, 5, n)
    p = 1 / (1 + np.exp(-(-1.5 + 0.04 * (income / 1000 - 60) + 1.5 * eng)))
    treated = (rng.uniform(size=n) < p).astype(int)
    outcome = (0.05 + 0.002 * age + 0.6 * eng + 0.15 * treated
               + rng.normal(scale=0.05, size=n))
    df = pd.DataFrame({"age": age, "income": income, "prior_engagement": eng,
                       "treated": treated, "outcome": outcome})
    res = PropensityScoreMatcher(caliper=0.1).estimate(
        df, treatment="treated", outcome="outcome",
        covariates=["age", "income", "prior_engagement"],
    )
    assert abs(res.att - 0.15) < 0.08
    assert res.n_matched > 0
