"""In-process metrics + alert engine.

Production builds wire prometheus_client's multiproc collector onto the
same registry so the /metrics endpoint scrapes these counters and gauges
directly. The pacing alerts here are the same logic the off-process
alert evaluator runs against the warehouse aggregates.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field

import numpy as np


@dataclass
class Alert:
    severity: str   # info, warning, critical
    message: str
    metric: str
    value: float
    timestamp: float = field(default_factory=time.time)


class MetricsRegistry:
    """Lock-protected metrics store. Tracks latency, throughput, SLA, alerts."""

    SLA_TARGET = 0.9995

    def __init__(self, latency_window: int = 5000):
        self.latency_samples: deque[float] = deque(maxlen=latency_window)
        self.requests_total = 0
        self.errors_total = 0
        self._lock = threading.Lock()
        self.alerts: deque[Alert] = deque(maxlen=200)
        self._counters: dict[str, int] = {}
        self._gauges: dict[str, float] = {}

    def observe_latency(self, ms: float) -> None:
        with self._lock:
            self.latency_samples.append(ms)
            self.requests_total += 1
            if ms > 100.0:
                self.alerts.append(Alert(
                    severity="warning",
                    message=f"latency exceeded 100ms ({ms:.1f}ms)",
                    metric="bid_latency_ms",
                    value=ms,
                ))

    def record_error(self) -> None:
        with self._lock:
            self.errors_total += 1
            self.requests_total += 1

    def incr(self, name: str, n: int = 1) -> None:
        with self._lock:
            self._counters[name] = self._counters.get(name, 0) + n

    def gauge(self, name: str, value: float) -> None:
        with self._lock:
            self._gauges[name] = value

    def check_budget_pacing(self, campaign_id: str, spent: float, daily_budget: float,
                             elapsed_fraction: float) -> None:
        """Raise an alert when spend velocity diverges from clock velocity."""
        if daily_budget <= 0:
            return
        spend_fraction = spent / daily_budget
        if spend_fraction > elapsed_fraction * 1.5:
            self.alerts.append(Alert(
                severity="warning",
                message=f"campaign {campaign_id} pacing 1.5x ahead of schedule",
                metric="budget_pacing", value=spend_fraction,
            ))
        elif spend_fraction < elapsed_fraction * 0.5 and elapsed_fraction > 0.25:
            self.alerts.append(Alert(
                severity="info",
                message=f"campaign {campaign_id} underspending (50% behind)",
                metric="budget_pacing", value=spend_fraction,
            ))

    def percentiles(self) -> dict:
        if not self.latency_samples:
            return {"p50": 0.0, "p95": 0.0, "p99": 0.0}
        arr = np.asarray(self.latency_samples)
        return {
            "p50": float(np.percentile(arr, 50)),
            "p95": float(np.percentile(arr, 95)),
            "p99": float(np.percentile(arr, 99)),
        }

    def sla_compliance(self) -> float:
        if self.requests_total == 0:
            return 1.0
        success_rate = 1.0 - (self.errors_total / self.requests_total)
        return round(success_rate, 5)

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "latency_ms": self.percentiles(),
                "requests_total": self.requests_total,
                "errors_total": self.errors_total,
                "sla_compliance": self.sla_compliance(),
                "sla_target": self.SLA_TARGET,
                "sla_met": self.sla_compliance() >= self.SLA_TARGET,
                "counters": dict(self._counters),
                "gauges": dict(self._gauges),
                "recent_alerts": [
                    {"severity": a.severity, "message": a.message,
                     "metric": a.metric, "value": a.value, "ts": a.timestamp}
                    for a in list(self.alerts)[-10:]
                ],
            }
