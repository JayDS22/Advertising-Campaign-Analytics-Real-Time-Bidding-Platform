from src.streaming.events import AdEvent, EventType
from src.streaming.producer import AdEventProducer
from src.streaming.consumer import AdEventConsumer
from src.streaming.windowed_aggregator import WindowedAggregator


def test_event_round_trip_json():
    e = AdEvent(event_type=EventType.IMPRESSION, campaign_id="c1",
                user_id="u1", clearing_price=0.01, revenue=0.01)
    s = e.to_json()
    e2 = AdEvent.from_json(s)
    assert e2.event_type == EventType.IMPRESSION and e2.campaign_id == "c1"


def test_producer_consumer_inmemory_roundtrip():
    prod = AdEventProducer()
    for i in range(50):
        prod.send(AdEvent(event_type=EventType.IMPRESSION,
                          campaign_id=f"c{i % 3}", user_id=f"u{i}"))
    consumer = AdEventConsumer(producer=prod)
    seen = []
    n = consumer.consume_inmemory(seen.append)
    assert n == 50 and len(seen) == 50


def test_windowed_aggregator():
    agg = WindowedAggregator(window_seconds=10, retain_windows=5)
    for _ in range(10):
        agg.ingest(AdEvent(event_type=EventType.IMPRESSION,
                           campaign_id="c1", clearing_price=0.005,
                           revenue=0.005))
    for _ in range(2):
        agg.ingest(AdEvent(event_type=EventType.CLICK, campaign_id="c1"))
    agg.ingest(AdEvent(event_type=EventType.CONVERSION, campaign_id="c1",
                       conversion_value=20.0))
    out = agg.aggregate_all()
    assert "c1" in out
    m = out["c1"]
    assert m.impressions == 10 and m.clicks == 2 and m.conversions == 1
    assert m.ctr > 0 and m.revenue > 0
