"""Kafka consumer dispatch. Hydrates the windowed aggregator and the
warehouse landing zone. Same callback shape regardless of source.
"""
from __future__ import annotations

from typing import Callable, Iterable, Optional

from .events import AdEvent
from .producer import AdEventProducer


class AdEventConsumer:
    """Two ingestion modes: drain the producer's in-memory buffer, or
    iterate an arbitrary AdEvent iterable. Real Kafka subscribe is wired
    in production via the same handler signature.
    """

    def __init__(self, producer: Optional[AdEventProducer] = None,
                 bootstrap_servers: str = "localhost:9092",
                 group_id: str = "rtb-analytics"):
        self.producer = producer  # used as in-memory fallback source
        self.bootstrap_servers = bootstrap_servers
        self.group_id = group_id

    def consume_inmemory(self, handler: Callable[[AdEvent], None]) -> int:
        """Drain the producer's local buffer. Returns the number of events handled."""
        if self.producer is None:
            return 0
        events = self.producer.drain_buffer()
        for _topic, ev in events:
            handler(ev)
        return len(events)

    def consume_iterable(self, events: Iterable[AdEvent],
                         handler: Callable[[AdEvent], None]) -> int:
        n = 0
        for ev in events:
            handler(ev)
            n += 1
        return n
