"""Streaming pipeline (Kafka producer/consumer + Spark windowed aggregations)."""
from .producer import AdEventProducer
from .consumer import AdEventConsumer
from .windowed_aggregator import WindowedAggregator
from .events import AdEvent, EventType

__all__ = [
    "AdEventProducer", "AdEventConsumer", "WindowedAggregator",
    "AdEvent", "EventType",
]
