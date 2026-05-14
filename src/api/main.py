"""FastAPI application. Hosts the bid endpoint, analytics, A/B + causal APIs.

Most endpoints operate on the shared :class:`PlatformState` singleton so the
demo can reflect cumulative state across requests.
"""
from __future__ import annotations

import os
import random
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from src.api.state import PlatformState
from src.causal_inference.did import DifferenceInDifferences
from src.causal_inference.propensity_matching import PropensityScoreMatcher
from src.experimentation.ab_test import ABTest, BenjaminiHochberg
from src.rtb_engine.bidder import BidRequest
from src.streaming.events import AdEvent, EventType


BASE_DIR = Path(__file__).resolve().parents[2]
DEMO_DIR = BASE_DIR / "demo"


app = FastAPI(
    title="Advertising Campaign Analytics & RTB Platform",
    description=("Real-time bidding engine, streaming analytics, A/B testing, "
                 "causal inference, and advertiser dashboards."),
    version="1.0.0",
)

app.mount("/static", StaticFiles(directory=str(DEMO_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(DEMO_DIR / "templates"))


# ---------------------------- Pydantic schemas ---------------------------- #

class BidReqIn(BaseModel):
    user_id: str = Field(..., examples=["user-abc123"])
    device_type: str = Field("mobile", examples=["mobile", "desktop", "tablet", "ctv"])
    geo_country: str = Field("US", examples=["US"])
    geo_city: str = Field("New York")
    site_domain: str = Field("nytimes.com")
    ad_slot_id: str = Field("slot-1")
    ad_format: str = Field("banner")
    width: int = 300
    height: int = 250
    floor_price: float = 0.001
    user_segments: list[str] = Field(default_factory=list)


class EventIn(BaseModel):
    event_type: str
    campaign_id: str
    creative_id: str
    user_id: str = ""
    advertiser_id: str = ""
    geo_country: str = "US"
    device_type: str = "mobile"
    site_domain: str = ""
    clearing_price: float = 0.0
    conversion_value: Optional[float] = None


class ABTestIn(BaseModel):
    control_success: int
    control_total: int
    treatment_success: int
    treatment_total: int
    metric_name: str = "ctr"
    alpha: float = 0.01


class SampleSizeIn(BaseModel):
    baseline_rate: float
    mde: float
    alpha: float = 0.05
    power: float = 0.8


class DiDIn(BaseModel):
    n_units: int = 200
    pre_periods: int = 6
    post_periods: int = 6
    true_effect: float = 0.15


class PSMIn(BaseModel):
    n_users: int = 800
    treatment_effect: float = 0.12


# ---------------------------- Helpers ---------------------------- #


def _state() -> PlatformState:
    return PlatformState.get()


# ---------------------------- UI ---------------------------- #


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


# ---------------------------- RTB ---------------------------- #


@app.post("/api/bid")
def post_bid(payload: BidReqIn):
    state = _state()
    req = BidRequest(
        request_id=str(uuid.uuid4()),
        user_id=payload.user_id,
        device_type=payload.device_type,
        geo_country=payload.geo_country,
        geo_city=payload.geo_city,
        site_domain=payload.site_domain,
        ad_slot_id=payload.ad_slot_id,
        ad_format=payload.ad_format,
        width=payload.width,
        height=payload.height,
        floor_price=payload.floor_price,
        user_segments=payload.user_segments,
    )
    resp = state.engine.bid(req)
    state.metrics.observe_latency(resp.decision_latency_ms)
    state.metrics.incr("bid_requests")
    if resp.bid_price > 0:
        state.metrics.incr("bid_responses")
        # Stand-in for win-notice ingest. Bernoulli draw against the engine's
        # win probability; production replaces this with the actual SSP callback.
        if random.random() < resp.win_probability:
            state.engine.record_win(resp.campaign_id, resp.bid_price)
            state.emit(AdEvent(
                event_type=EventType.IMPRESSION,
                user_id=req.user_id,
                campaign_id=resp.campaign_id,
                advertiser_id=resp.advertiser_id,
                creative_id=resp.creative_id,
                site_domain=req.site_domain,
                geo_country=req.geo_country,
                device_type=req.device_type,
                bid_price=resp.bid_price,
                clearing_price=resp.bid_price,
                revenue=resp.bid_price,
            ))
    return {
        "request_id": resp.request_id,
        "bid_price": resp.bid_price,
        "creative_id": resp.creative_id,
        "campaign_id": resp.campaign_id,
        "advertiser_id": resp.advertiser_id,
        "win_probability": resp.win_probability,
        "expected_value": resp.expected_value,
        "decision_latency_ms": resp.decision_latency_ms,
        "no_bid_reason": resp.no_bid_reason,
    }


@app.post("/api/events")
def post_event(payload: EventIn):
    state = _state()
    try:
        evt_type = EventType(payload.event_type)
    except ValueError:
        raise HTTPException(400, f"unknown event_type: {payload.event_type}")
    ev = AdEvent(
        event_type=evt_type,
        user_id=payload.user_id,
        campaign_id=payload.campaign_id,
        creative_id=payload.creative_id,
        advertiser_id=payload.advertiser_id,
        geo_country=payload.geo_country,
        device_type=payload.device_type,
        site_domain=payload.site_domain,
        clearing_price=payload.clearing_price,
        revenue=payload.clearing_price,
        conversion_value=payload.conversion_value,
    )
    state.emit(ev)
    return {"status": "accepted", "event_id": ev.event_id}


@app.post("/api/simulate")
def simulate(n: int = 100):
    """Inject N synthetic bid requests with downstream wins / clicks / convs."""
    if n < 1 or n > 5000:
        raise HTTPException(400, "n must be between 1 and 5000")
    state = _state()
    from src.api.seed_data import random_user
    bids = 0
    wins = 0
    for _ in range(n):
        u = random_user()
        req = BidRequest(
            request_id=str(uuid.uuid4()), user_id=u["user_id"],
            device_type=u["device_type"], geo_country=u["geo_country"],
            geo_city=u["geo_city"], site_domain=u["site_domain"],
            ad_slot_id="slot-x", ad_format="banner", width=300, height=250,
            floor_price=0.001, user_segments=u["user_segments"],
        )
        resp = state.engine.bid(req)
        state.metrics.observe_latency(resp.decision_latency_ms)
        if resp.bid_price > 0:
            bids += 1
            if random.random() < resp.win_probability:
                wins += 1
                state.engine.record_win(resp.campaign_id, resp.bid_price)
                state.emit(AdEvent(
                    event_type=EventType.IMPRESSION, user_id=u["user_id"],
                    campaign_id=resp.campaign_id, advertiser_id=resp.advertiser_id,
                    creative_id=resp.creative_id, site_domain=u["site_domain"],
                    geo_country=u["geo_country"], device_type=u["device_type"],
                    bid_price=resp.bid_price, clearing_price=resp.bid_price,
                    revenue=resp.bid_price,
                ))
                if random.random() < 0.025:
                    state.emit(AdEvent(
                        event_type=EventType.CLICK, user_id=u["user_id"],
                        campaign_id=resp.campaign_id,
                        advertiser_id=resp.advertiser_id,
                        creative_id=resp.creative_id,
                        site_domain=u["site_domain"],
                        geo_country=u["geo_country"], device_type=u["device_type"],
                    ))
                    if random.random() < 0.06:
                        state.emit(AdEvent(
                            event_type=EventType.CONVERSION, user_id=u["user_id"],
                            campaign_id=resp.campaign_id,
                            advertiser_id=resp.advertiser_id,
                            creative_id=resp.creative_id,
                            site_domain=u["site_domain"],
                            geo_country=u["geo_country"], device_type=u["device_type"],
                            conversion_value=random.uniform(20, 200),
                        ))
    return {"requests": n, "bids": bids, "wins": wins,
            "engine_stats": state.engine.stats()}


# ---------------------------- Analytics ---------------------------- #


@app.get("/api/campaigns")
def list_campaigns():
    state = _state()
    out = []
    aggregates = state.aggregator.aggregate_all()
    for c in state.engine.campaigns.values():
        agg = aggregates.get(c.campaign_id)
        impressions = agg.impressions if agg else 0
        clicks = agg.clicks if agg else 0
        conversions = agg.conversions if agg else 0
        revenue = agg.revenue if agg else 0.0
        ctr = clicks / impressions if impressions else 0.0
        cvr = conversions / clicks if clicks else 0.0
        cpa = revenue / conversions if conversions else 0.0
        cpm = (revenue / impressions * 1000.0) if impressions else 0.0
        out.append({
            "campaign_id": c.campaign_id,
            "advertiser_id": c.advertiser_id,
            "advertiser_name": state.advertisers.get(c.advertiser_id, c.advertiser_id),
            "bid_cpm": round(c.bid_cpm, 2),
            "budget_remaining": round(c.budget_remaining, 2),
            "daily_budget": round(c.daily_budget, 2),
            "daily_spent": round(c.daily_spent, 2),
            "is_active": c.is_active,
            "kpis": {
                "impressions": impressions,
                "clicks": clicks,
                "conversions": conversions,
                "revenue": round(revenue, 2),
                "ctr": round(ctr, 4),
                "cvr": round(cvr, 4),
                "cpa": round(cpa, 2),
                "cpm": round(cpm, 2),
                "roas": round((conversions * 80.0) / max(revenue, 1e-6), 2),
            },
            "target_segments": c.target_segments,
            "target_geos": c.target_geos,
            "target_devices": c.target_devices,
        })
    out.sort(key=lambda x: x["kpis"]["revenue"], reverse=True)
    return {"campaigns": out}


@app.get("/api/timeseries")
def timeseries():
    state = _state()
    points = []
    for w in state.aggregator.all_windows():
        impressions = sum(m.impressions for m in w.by_campaign.values())
        clicks = sum(m.clicks for m in w.by_campaign.values())
        conversions = sum(m.conversions for m in w.by_campaign.values())
        revenue = sum(m.revenue for m in w.by_campaign.values())
        points.append({
            "ts": int(w.window_start * 1000),
            "impressions": impressions,
            "clicks": clicks,
            "conversions": conversions,
            "revenue": round(revenue, 2),
        })
    return {"points": points}


@app.get("/api/metrics")
def metrics():
    state = _state()
    return {
        "engine": state.engine.stats(),
        "monitoring": state.metrics.snapshot(),
        "warehouse": {
            "tables": list(state.warehouse._tables.keys()),
            "row_counts": {t: len(rs) for t, rs in state.warehouse._tables.items()},
            "storage_savings_pct": state.warehouse.storage_savings_pct(),
        },
        "feature_store": state.feature_store.stats(),
        "producer": state.producer.stats(),
    }


# ---------------------------- A/B Test + MAB ---------------------------- #


@app.get("/api/mab")
def mab_snapshot():
    state = _state()
    arms = state.mab.snapshot()
    next_arm = state.mab.select_arm() if state.mab.arms else None
    return {"arms": arms, "next_recommended_arm": next_arm}


@app.post("/api/ab_test")
def ab_test(payload: ABTestIn):
    if min(payload.control_total, payload.treatment_total) <= 0:
        raise HTTPException(400, "totals must be positive")
    if payload.control_success > payload.control_total or \
       payload.treatment_success > payload.treatment_total:
        raise HTTPException(400, "successes cannot exceed totals")
    res = ABTest.proportion_test(
        payload.control_success, payload.control_total,
        payload.treatment_success, payload.treatment_total,
        metric_name=payload.metric_name, alpha=payload.alpha,
    )
    return res.__dict__


@app.post("/api/sample_size")
def sample_size(payload: SampleSizeIn):
    n = ABTest.required_sample_size(payload.baseline_rate, payload.mde,
                                     payload.alpha, payload.power)
    return {"required_per_arm": n, "total": n * 2}


@app.get("/api/fdr")
def fdr_demo():
    """Run BH on a 10-effect / 40-null mix and report uncorrected vs BH counts."""
    rng = np.random.default_rng(7)
    # 10 true effects, 40 nulls
    z_true = rng.normal(loc=2.5, size=10)
    z_null = rng.normal(loc=0.0, size=40)
    from scipy import stats as sstats
    p = (1 - sstats.norm.cdf(np.abs(np.concatenate([z_true, z_null])))) * 2
    rejected = BenjaminiHochberg.correct(p.tolist(), fdr=0.05)
    return {
        "n_tests": len(p),
        "n_significant_uncorrected": int((p < 0.05).sum()),
        "n_significant_bh": int(sum(rejected)),
        "fdr_target": 0.05,
        "p_values_sorted": [round(x, 4) for x in sorted(p.tolist())],
    }


# ---------------------------- Causal inference ---------------------------- #


@app.post("/api/did")
def did_endpoint(payload: DiDIn):
    rng = np.random.default_rng(11)
    rows = []
    for u in range(payload.n_units):
        treated = int(u < payload.n_units // 2)
        unit_baseline = rng.normal(loc=10.0, scale=2.0)
        unit_trend = rng.normal(loc=0.05, scale=0.05)
        for t in range(-payload.pre_periods, payload.post_periods):
            post = int(t >= 0)
            outcome = (unit_baseline + unit_trend * t
                       + payload.true_effect * treated * post
                       + rng.normal(scale=1.0))
            rows.append({
                "unit_id": u, "time": t, "treated": treated,
                "post": post, "outcome": outcome,
            })
    df = pd.DataFrame(rows)
    res = DifferenceInDifferences().fit(df)
    return res.__dict__


@app.post("/api/psm")
def psm_endpoint(payload: PSMIn):
    rng = np.random.default_rng(23)
    n = payload.n_users
    age = rng.normal(35, 10, n)
    income = rng.normal(60_000, 20_000, n)
    prior_engagement = rng.beta(2, 5, n)
    # Treatment more likely for engaged + middle-income users
    logit = -1.5 + 0.04 * (income / 1000 - 60) + 1.5 * prior_engagement
    p_treat = 1 / (1 + np.exp(-logit))
    treated = (rng.uniform(size=n) < p_treat).astype(int)
    outcome = (0.05 + 0.002 * age + 0.6 * prior_engagement
               + payload.treatment_effect * treated
               + rng.normal(scale=0.05, size=n))
    df = pd.DataFrame({
        "age": age, "income": income, "prior_engagement": prior_engagement,
        "treated": treated, "outcome": outcome,
    })
    res = PropensityScoreMatcher(caliper=0.1).estimate(
        df, treatment="treated", outcome="outcome",
        covariates=["age", "income", "prior_engagement"],
    )
    return res.__dict__


# ---------------------------- Health ---------------------------- #


@app.get("/health")
def health():
    return {"status": "ok", "ts": datetime.utcnow().isoformat()}
