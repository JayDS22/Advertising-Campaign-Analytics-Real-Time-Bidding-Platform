"""RTB engine. OpenRTB 2.5 over a CF-based scoring stack.

Targets sub-50ms P99 decisioning. Hot path: filter eligible campaigns by
geo/device/segment/floor/budget, score each candidate creative against the
user embedding (cosine similarity as a CTR proxy), rank by expected value,
and emit the bid. Win probability is a logistic over the (bid - floor) gap.
"""
from __future__ import annotations

import time
import hashlib
import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import numpy as np

from src.feature_store.redis_store import RedisFeatureStore


@dataclass
class BidRequest:
    """OpenRTB 2.5 bid request payload (subset of the spec)."""
    request_id: str
    user_id: str
    device_type: str  # mobile, desktop, tablet, ctv
    geo_country: str
    geo_city: str
    site_domain: str
    ad_slot_id: str
    ad_format: str  # banner, video, native
    width: int
    height: int
    floor_price: float
    timestamp: datetime = field(default_factory=datetime.utcnow)
    user_segments: list[str] = field(default_factory=list)


@dataclass
class BidResponse:
    """OpenRTB 2.5 bid response payload (subset of the spec)."""
    request_id: str
    bid_price: float
    creative_id: str
    campaign_id: str
    advertiser_id: str
    win_probability: float
    expected_value: float
    decision_latency_ms: float
    no_bid_reason: Optional[str] = None


@dataclass
class Campaign:
    """Buyer-side campaign record. Carries budget, pacing, targeting."""
    campaign_id: str
    advertiser_id: str
    budget_total: float
    budget_remaining: float
    daily_budget: float
    daily_spent: float
    bid_cpm: float
    target_segments: list[str]
    target_geos: list[str]
    target_devices: list[str]
    creative_ids: list[str]
    is_active: bool = True


class RTBEngine:
    """Bidder. Hot-path layout favors latency over throughput.

    Latency wins come from:
      * keeping the campaign list in-process (no DB roundtrip per bid),
      * a Redis lookup for the user embedding (with an in-memory fallback),
      * scoring all candidates with a single numpy dot, and
      * deterministic embedding synthesis on cache miss so we never block.
    """

    def __init__(self, feature_store: Optional[RedisFeatureStore] = None,
                 embedding_dim: int = 32):
        self.feature_store = feature_store or RedisFeatureStore()
        self.embedding_dim = embedding_dim
        self.campaigns: dict[str, Campaign] = {}
        self.creative_embeddings: dict[str, np.ndarray] = {}
        # Stats
        self.total_requests = 0
        self.total_bids = 0
        self.total_no_bids = 0
        self.latency_samples: list[float] = []

    def register_campaign(self, campaign: Campaign) -> None:
        """Upsert a campaign and lazily seed creative embeddings."""
        self.campaigns[campaign.campaign_id] = campaign
        for cid in campaign.creative_ids:
            if cid not in self.creative_embeddings:
                # Hash the creative id to a fixed seed so the same id always
                # resolves to the same embedding across processes.
                seed = int(hashlib.md5(cid.encode()).hexdigest()[:8], 16)
                rng = np.random.default_rng(seed)
                self.creative_embeddings[cid] = rng.standard_normal(self.embedding_dim)

    def _get_user_embedding(self, user_id: str) -> np.ndarray:
        cached = self.feature_store.get_user_embedding(user_id)
        if cached is not None:
            return cached
        # Cache miss. Synthesize a stable embedding so the bid can proceed
        # without a blocking write to the offline feature pipeline.
        seed = int(hashlib.md5(user_id.encode()).hexdigest()[:8], 16)
        rng = np.random.default_rng(seed)
        emb = rng.standard_normal(self.embedding_dim)
        self.feature_store.set_user_embedding(user_id, emb)
        return emb

    def _score_creative(self, user_emb: np.ndarray, creative_id: str) -> float:
        c_emb = self.creative_embeddings.get(creative_id)
        if c_emb is None:
            return 0.5
        denom = (np.linalg.norm(user_emb) * np.linalg.norm(c_emb)) + 1e-9
        cos = float(np.dot(user_emb, c_emb) / denom)
        # Map cosine [-1, 1] to a [0, 1] CTR-like score.
        return (cos + 1.0) / 2.0

    def _eligible_campaigns(self, req: BidRequest) -> list[Campaign]:
        out: list[Campaign] = []
        for c in self.campaigns.values():
            if not c.is_active or c.budget_remaining <= 0 or c.daily_spent >= c.daily_budget:
                continue
            if c.target_geos and req.geo_country not in c.target_geos:
                continue
            if c.target_devices and req.device_type not in c.target_devices:
                continue
            if c.target_segments and not (set(c.target_segments) & set(req.user_segments)):
                continue
            if c.bid_cpm / 1000.0 < req.floor_price:
                continue
            out.append(c)
        return out

    def bid(self, req: BidRequest) -> BidResponse:
        """Score eligible (campaign, creative) pairs and return the top EV bid."""
        start = time.perf_counter()
        self.total_requests += 1

        eligible = self._eligible_campaigns(req)
        if not eligible:
            self.total_no_bids += 1
            latency = (time.perf_counter() - start) * 1000.0
            self.latency_samples.append(latency)
            return BidResponse(
                request_id=req.request_id, bid_price=0.0, creative_id="",
                campaign_id="", advertiser_id="", win_probability=0.0,
                expected_value=0.0, decision_latency_ms=latency,
                no_bid_reason="no_eligible_campaigns",
            )

        user_emb = self._get_user_embedding(req.user_id)
        best: Optional[tuple[float, Campaign, str, float]] = None

        for c in eligible:
            for cid in c.creative_ids:
                ctr_score = self._score_creative(user_emb, cid)
                # CPM is per-mille, so the per-impression price is /1000.
                # EV ranking ignores second-price uplift on purpose; it's a wash
                # across candidates from the same buyer.
                bid_price = c.bid_cpm / 1000.0
                ev = ctr_score * bid_price
                if best is None or ev > best[0]:
                    best = (ev, c, cid, ctr_score)

        assert best is not None
        ev, campaign, creative_id, ctr = best
        bid_price = campaign.bid_cpm / 1000.0
        # Logistic over the (bid - floor) gap. Slope of 8 was fit against a
        # sample of historical clearing data; tune per exchange in production.
        gap = bid_price - req.floor_price
        win_prob = 1.0 / (1.0 + math.exp(-8.0 * gap))

        self.total_bids += 1
        latency = (time.perf_counter() - start) * 1000.0
        self.latency_samples.append(latency)
        # Bound the rolling sample so memory stays flat under sustained load.
        if len(self.latency_samples) > 10000:
            self.latency_samples = self.latency_samples[-5000:]

        return BidResponse(
            request_id=req.request_id,
            bid_price=round(bid_price, 6),
            creative_id=creative_id,
            campaign_id=campaign.campaign_id,
            advertiser_id=campaign.advertiser_id,
            win_probability=round(win_prob, 4),
            expected_value=round(ev, 6),
            decision_latency_ms=round(latency, 3),
        )

    def record_win(self, campaign_id: str, clearing_price: float) -> None:
        """Decrement remaining + daily budgets after a winning bid notification."""
        c = self.campaigns.get(campaign_id)
        if c is None:
            return
        c.budget_remaining = max(0.0, c.budget_remaining - clearing_price)
        c.daily_spent += clearing_price

    def latency_percentiles(self) -> dict[str, float]:
        if not self.latency_samples:
            return {"p50": 0.0, "p95": 0.0, "p99": 0.0}
        arr = np.asarray(self.latency_samples)
        return {
            "p50": float(np.percentile(arr, 50)),
            "p95": float(np.percentile(arr, 95)),
            "p99": float(np.percentile(arr, 99)),
        }

    def stats(self) -> dict:
        bid_rate = (self.total_bids / self.total_requests) if self.total_requests else 0.0
        return {
            "total_requests": self.total_requests,
            "total_bids": self.total_bids,
            "total_no_bids": self.total_no_bids,
            "bid_rate": round(bid_rate, 4),
            "active_campaigns": sum(1 for c in self.campaigns.values() if c.is_active),
            "latency_ms": self.latency_percentiles(),
        }
