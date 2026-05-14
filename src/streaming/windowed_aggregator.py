"""Tumbling-window roll-up. Mirrors the semantics of the production Spark
Structured Streaming job (``groupBy(window(...), 'campaign_id')``) inside
the API process so the demo stays runnable without a JVM.

Per (window, campaign): impression count, click count, conversion count,
revenue, derived rates (CTR, CVR, CPC, CPM).
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

from .events import AdEvent, EventType


@dataclass
class WindowedMetrics:
    impressions: int = 0
    clicks: int = 0
    conversions: int = 0
    revenue: float = 0.0
    bid_requests: int = 0

    @property
    def ctr(self) -> float:
        return self.clicks / self.impressions if self.impressions else 0.0

    @property
    def cvr(self) -> float:
        return self.conversions / self.clicks if self.clicks else 0.0

    @property
    def cpc(self) -> float:
        return self.revenue / self.clicks if self.clicks else 0.0

    @property
    def cpm(self) -> float:
        return (self.revenue / self.impressions * 1000.0) if self.impressions else 0.0


@dataclass
class WindowState:
    window_start: float
    window_end: float
    by_campaign: dict[str, WindowedMetrics] = field(default_factory=lambda: defaultdict(WindowedMetrics))


class WindowedAggregator:
    """Thread-safe tumbling-window aggregator. Bounded retention."""

    def __init__(self, window_seconds: int = 60, retain_windows: int = 60):
        self.window_seconds = window_seconds
        self.retain_windows = retain_windows
        self._windows: list[WindowState] = []
        self._lock = threading.Lock()

    def _floor_window(self, ts: float) -> float:
        return ts - (ts % self.window_seconds)

    def _get_or_create(self, ts: float) -> WindowState:
        start = self._floor_window(ts)
        for w in self._windows:
            if w.window_start == start:
                return w
        w = WindowState(window_start=start, window_end=start + self.window_seconds)
        self._windows.append(w)
        # Cap retention so memory is bounded under sustained ingestion.
        if len(self._windows) > self.retain_windows:
            self._windows.sort(key=lambda x: x.window_start)
            self._windows = self._windows[-self.retain_windows:]
        return w

    def ingest(self, event: AdEvent) -> None:
        ts = time.time()
        with self._lock:
            window = self._get_or_create(ts)
            m = window.by_campaign[event.campaign_id]
            if event.event_type == EventType.IMPRESSION:
                m.impressions += 1
                m.revenue += event.clearing_price
            elif event.event_type == EventType.CLICK:
                m.clicks += 1
            elif event.event_type == EventType.CONVERSION:
                m.conversions += 1
                if event.conversion_value is not None:
                    m.revenue += event.conversion_value
            elif event.event_type == EventType.BID_REQUEST:
                m.bid_requests += 1

    def latest_window(self) -> Optional[WindowState]:
        with self._lock:
            if not self._windows:
                return None
            return max(self._windows, key=lambda w: w.window_start)

    def all_windows(self) -> list[WindowState]:
        with self._lock:
            return sorted(self._windows, key=lambda w: w.window_start)

    def aggregate_all(self) -> dict[str, WindowedMetrics]:
        """Roll all retained windows into a per-campaign total."""
        out: dict[str, WindowedMetrics] = defaultdict(WindowedMetrics)
        with self._lock:
            for w in self._windows:
                for cid, m in w.by_campaign.items():
                    a = out[cid]
                    a.impressions += m.impressions
                    a.clicks += m.clicks
                    a.conversions += m.conversions
                    a.revenue += m.revenue
                    a.bid_requests += m.bid_requests
        return dict(out)
