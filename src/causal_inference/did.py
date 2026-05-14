"""Difference-in-Differences. Used for campaign incrementality / lift studies."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf


@dataclass
class DiDResult:
    treatment_effect: float        # DiD point estimate (interaction coef)
    se: float                      # cluster-robust standard error
    t_stat: float
    p_value: float
    ci95_low: float
    ci95_high: float
    n_obs: int
    pre_period_diff: float         # parallel-trends sanity diff (pre only)


class DifferenceInDifferences:
    """Two-way DiD fit via OLS with SEs clustered on the panel id.

    Long-format input with columns:
        unit_id  : panel id (advertiser, market, user cohort)
        time     : period (int or date)
        treated  : 0/1 group flag (time-invariant)
        post     : 0/1 post-intervention flag
        outcome  : continuous outcome (conversions, ROAS, etc.)
    """

    def fit(self, df: pd.DataFrame, cluster_col: str = "unit_id") -> DiDResult:
        required = {"unit_id", "time", "treated", "post", "outcome"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"missing columns: {missing}")
        df = df.copy()
        df["did"] = df["treated"] * df["post"]
        model = smf.ols(
            "outcome ~ treated + post + did",
            data=df,
        ).fit(cov_type="cluster", cov_kwds={"groups": df[cluster_col]})

        coef = float(model.params["did"])
        se = float(model.bse["did"])
        t = float(model.tvalues["did"])
        p = float(model.pvalues["did"])
        lo, hi = model.conf_int(alpha=0.05).loc["did"].tolist()

        # Sanity diff: group-mean gap in the pre-period. Should be small and
        # stable if the parallel-trends assumption holds.
        pre = df[df["post"] == 0]
        pre_diff = (pre[pre["treated"] == 1]["outcome"].mean()
                    - pre[pre["treated"] == 0]["outcome"].mean())

        return DiDResult(
            treatment_effect=round(coef, 6),
            se=round(se, 6),
            t_stat=round(t, 4),
            p_value=round(p, 6),
            ci95_low=round(float(lo), 6),
            ci95_high=round(float(hi), 6),
            n_obs=int(df.shape[0]),
            pre_period_diff=round(float(pre_diff), 6),
        )
