"""Process-wide platform state. Wires the bidder, streaming, warehouse,
metrics, MAB, and feature store together behind a thread-safe singleton.
"""
from __future__ import annotations

import threading
import uuid
from typing import Optional

from src.experimentation.thompson_sampling import ThompsonSamplingMAB
from src.feature_store.redis_store import RedisFeatureStore
from src.monitoring.metrics import MetricsRegistry
from src.rtb_engine.bidder import RTBEngine
from src.streaming.events import AdEvent, EventType
from src.streaming.producer import AdEventProducer
from src.streaming.windowed_aggregator import WindowedAggregator
from src.warehouse.redshift_loader import RedshiftLoader
from src.api.seed_data import (
    advertiser_lookup, make_demo_campaigns, synthetic_event_stream,
)


class PlatformState:
    """Composition root. One instance per process; lazily built on first use."""

    _instance: Optional["PlatformState"] = None
    _lock = threading.Lock()

    def __init__(self):
        self.feature_store = RedisFeatureStore()
        self.engine = RTBEngine(feature_store=self.feature_store)
        self.producer = AdEventProducer()
        self.aggregator = WindowedAggregator(window_seconds=10, retain_windows=60)
        self.warehouse = RedshiftLoader()
        self.metrics = MetricsRegistry()
        self.mab = ThompsonSamplingMAB()
        self.advertisers = advertiser_lookup()

        # Register demo campaigns and prime the bandit with one arm per creative.
        for c in make_demo_campaigns():
            self.engine.register_campaign(c)
            for creative in c.creative_ids:
                self.mab.add_arm(creative)

        # Backfill ~2k synthetic events so the dashboard has data to render.
        seed = synthetic_event_stream(list(self.engine.campaigns.values()), n=2000)
        for ev in seed:
            self.aggregator.ingest(ev)
            self._land_in_warehouse(ev)
            if ev.event_type in (EventType.IMPRESSION, EventType.CLICK):
                self.mab.update(ev.creative_id, 1 if ev.event_type == EventType.CLICK else 0)

    @classmethod
    def get(cls) -> "PlatformState":
        with cls._lock:
            if cls._instance is None:
                cls._instance = PlatformState()
            return cls._instance

    def _land_in_warehouse(self, ev: AdEvent) -> None:
        table = {
            EventType.IMPRESSION: "fact_impression",
            EventType.CLICK: "fact_click",
            EventType.CONVERSION: "fact_conversion",
            EventType.BID_REQUEST: "fact_bid_request",
            EventType.BID_RESPONSE: "fact_bid_response",
            EventType.VIEWABILITY: "fact_viewability",
        }.get(ev.event_type)
        if table is None:
            return
        self.warehouse.load(table, [{
            "event_id": ev.event_id,
            "ts": ev.timestamp,
            "campaign_id": ev.campaign_id,
            "creative_id": ev.creative_id,
            "user_id": ev.user_id,
            "geo_country": ev.geo_country,
            "device_type": ev.device_type,
            "revenue": ev.revenue,
            "clearing_price": ev.clearing_price,
            "conversion_value": ev.conversion_value,
        }])

    def emit(self, ev: AdEvent) -> None:
        """Fan an event through the producer, aggregator, warehouse, and bandit."""
        self.producer.send(ev)
        self.aggregator.ingest(ev)
        self._land_in_warehouse(ev)
        if ev.event_type == EventType.IMPRESSION:
            self.mab.update(ev.creative_id, 0)
            self.metrics.incr("impressions")
        elif ev.event_type == EventType.CLICK:
            self.mab.update(ev.creative_id, 1)
            self.metrics.incr("clicks")
        elif ev.event_type == EventType.CONVERSION:
            self.metrics.incr("conversions")

    def new_event_id(self) -> str:
        return str(uuid.uuid4())
