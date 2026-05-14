"""Kafka producer for ad events. Falls back to a bounded in-process deque
when the broker is unreachable so the local demo and the test suite both
exercise the publish path without standing up a cluster.
"""
from __future__ import annotations

from collections import deque
from typing import Optional

from .events import AdEvent

try:
    from kafka import KafkaProducer  # type: ignore
    HAS_KAFKA = True
except ImportError:
    HAS_KAFKA = False


class AdEventProducer:
    """Send AdEvent records to per-event-type topics.

    Producer config: acks=all, gzip, retries=3, linger_ms=5. The linger
    is intentionally small so click/conversion latency stays low at the
    cost of a slightly worse compression ratio.
    """

    def __init__(self, bootstrap_servers: str = "localhost:9092",
                 topic_prefix: str = "ads", buffer_size: int = 100_000):
        self.topic_prefix = topic_prefix
        self.buffer: deque[tuple[str, AdEvent]] = deque(maxlen=buffer_size)
        self._producer: Optional["KafkaProducer"] = None
        if HAS_KAFKA:
            try:
                self._producer = KafkaProducer(
                    bootstrap_servers=bootstrap_servers,
                    value_serializer=lambda v: v.encode("utf-8"),
                    key_serializer=lambda v: v.encode("utf-8") if v else None,
                    acks="all",
                    retries=3,
                    linger_ms=5,
                    compression_type="gzip",
                )
            except Exception:
                self._producer = None

    def topic_for(self, event: AdEvent) -> str:
        return f"{self.topic_prefix}.{event.event_type.value}"

    def send(self, event: AdEvent) -> None:
        topic = self.topic_for(event)
        if self._producer is not None:
            try:
                self._producer.send(topic, key=event.user_id, value=event.to_json())
                return
            except Exception:
                pass
        self.buffer.append((topic, event))

    def flush(self) -> None:
        if self._producer is not None:
            try:
                self._producer.flush(timeout=2)
            except Exception:
                pass

    def drain_buffer(self) -> list[tuple[str, AdEvent]]:
        out = list(self.buffer)
        self.buffer.clear()
        return out

    def stats(self) -> dict:
        return {
            "backend": "kafka" if self._producer is not None else "in-memory",
            "buffered": len(self.buffer),
        }
