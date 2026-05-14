"""Unified event record carried across Kafka topics. JSON over the wire.
Schema is intentionally Avro-compatible so the same dataclass can be
materialized into the warehouse without a translation layer.
"""
from __future__ import annotations

import enum
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Optional


class EventType(str, enum.Enum):
    BID_REQUEST = "bid_request"
    BID_RESPONSE = "bid_response"
    IMPRESSION = "impression"
    CLICK = "click"
    CONVERSION = "conversion"
    VIEWABILITY = "viewability"


@dataclass
class AdEvent:
    """One row across all topic types. Unused fields default to neutral values."""
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    event_type: EventType = EventType.IMPRESSION
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    user_id: str = ""
    campaign_id: str = ""
    advertiser_id: str = ""
    creative_id: str = ""
    site_domain: str = ""
    geo_country: str = ""
    device_type: str = ""
    bid_price: float = 0.0
    clearing_price: float = 0.0
    revenue: float = 0.0
    conversion_value: Optional[float] = None

    def to_json(self) -> str:
        d = asdict(self)
        d["event_type"] = self.event_type.value
        return json.dumps(d)

    @classmethod
    def from_json(cls, s: str) -> "AdEvent":
        d = json.loads(s)
        d["event_type"] = EventType(d["event_type"])
        return cls(**d)
