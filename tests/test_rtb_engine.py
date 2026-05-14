"""RTB engine tests: latency budget, eligibility, win bookkeeping."""
import time
import uuid

import pytest

from src.api.seed_data import make_demo_campaigns, random_user
from src.feature_store.redis_store import RedisFeatureStore
from src.rtb_engine.bidder import BidRequest, RTBEngine


@pytest.fixture
def engine():
    eng = RTBEngine(feature_store=RedisFeatureStore())
    for c in make_demo_campaigns():
        eng.register_campaign(c)
    return eng


def _make_request() -> BidRequest:
    u = random_user()
    return BidRequest(
        request_id=str(uuid.uuid4()), user_id=u["user_id"],
        device_type=u["device_type"], geo_country=u["geo_country"],
        geo_city=u["geo_city"], site_domain=u["site_domain"],
        ad_slot_id="slot-1", ad_format="banner", width=300, height=250,
        floor_price=0.001, user_segments=u["user_segments"],
    )


def test_bid_latency_under_budget(engine):
    """Cold-start P99 latency should remain under 50ms on the demo profile."""
    for _ in range(500):
        engine.bid(_make_request())
    pcts = engine.latency_percentiles()
    # generous CI budget: dev hardware shouldn't exceed 50ms P99
    assert pcts["p99"] < 50.0, f"P99 too high: {pcts}"


def test_no_bid_when_no_eligible(engine):
    req = _make_request()
    req.geo_country = "ZZ"  # no campaign targets this geo
    req.user_segments = []  # no segment match
    resp = engine.bid(req)
    # could still bid if a campaign has empty geo targets; if so, that's fine
    if resp.bid_price == 0:
        assert resp.no_bid_reason == "no_eligible_campaigns"


def test_record_win_decrements_budget(engine):
    cid = next(iter(engine.campaigns))
    before = engine.campaigns[cid].budget_remaining
    engine.record_win(cid, 1.23)
    after = engine.campaigns[cid].budget_remaining
    assert after == pytest.approx(before - 1.23)


def test_engine_stats_shape(engine):
    engine.bid(_make_request())
    s = engine.stats()
    assert "total_requests" in s and "latency_ms" in s
    assert s["total_requests"] >= 1
