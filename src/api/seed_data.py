"""Synthetic data factories. Campaigns, user contexts, and event streams.
Deterministic via fixed seeds so two runs of the demo line up.
"""
from __future__ import annotations

import random
import uuid
from datetime import datetime, timedelta

from faker import Faker

from src.rtb_engine.bidder import Campaign
from src.streaming.events import AdEvent, EventType


fake = Faker()
Faker.seed(42)
random.seed(42)

ADVERTISERS = [
    ("adv-nike", "Nike Performance"),
    ("adv-adidas", "Adidas Originals"),
    ("adv-spotify", "Spotify Premium"),
    ("adv-uber", "Uber Eats"),
    ("adv-airbnb", "Airbnb Stays"),
    ("adv-netflix", "Netflix Originals"),
    ("adv-tesla", "Tesla Model Y"),
    ("adv-apple", "Apple Vision Pro"),
]

SEGMENTS = ["sports_enthusiast", "music_lover", "foodie", "traveler",
            "binge_watcher", "ev_intender", "tech_early_adopter",
            "fashion_forward", "fitness_focused", "luxury_buyer"]

GEOS = ["US", "GB", "CA", "AU", "DE", "FR", "JP", "BR", "IN", "MX"]
DEVICES = ["mobile", "desktop", "tablet", "ctv"]
CITIES = ["New York", "London", "Toronto", "Sydney", "Berlin",
          "Paris", "Tokyo", "São Paulo", "Mumbai", "Mexico City"]


def make_demo_campaigns() -> list[Campaign]:
    out: list[Campaign] = []
    for i, (adv_id, adv_name) in enumerate(ADVERTISERS):
        cid = f"camp-{i+1:03d}"
        creatives = [f"{cid}-cr-{j+1}" for j in range(random.randint(2, 4))]
        out.append(Campaign(
            campaign_id=cid,
            advertiser_id=adv_id,
            budget_total=random.uniform(50_000, 500_000),
            budget_remaining=random.uniform(20_000, 400_000),
            daily_budget=random.uniform(2_000, 25_000),
            daily_spent=random.uniform(0, 5_000),
            bid_cpm=random.uniform(2.5, 18.0),
            target_segments=random.sample(SEGMENTS, k=random.randint(1, 4)),
            target_geos=random.sample(GEOS, k=random.randint(2, 6)),
            target_devices=random.sample(DEVICES, k=random.randint(2, 4)),
            creative_ids=creatives,
            is_active=True,
        ))
    return out


def random_user() -> dict:
    user_id = f"user-{uuid.uuid4().hex[:10]}"
    return {
        "user_id": user_id,
        "device_type": random.choice(DEVICES),
        "geo_country": random.choice(GEOS),
        "geo_city": random.choice(CITIES),
        "site_domain": fake.domain_name(),
        "user_segments": random.sample(SEGMENTS, k=random.randint(1, 3)),
    }


def synthetic_event_stream(campaigns: list[Campaign], n: int = 1000,
                            ctr_base: float = 0.025,
                            cvr_base: float = 0.04) -> list[AdEvent]:
    """Build N impressions plus a click/conversion funnel sampled from the rates."""
    events: list[AdEvent] = []
    base_ts = datetime.utcnow()
    for i in range(n):
        c = random.choice(campaigns)
        u = random_user()
        ts = base_ts - timedelta(seconds=random.randint(0, 3600))
        creative = random.choice(c.creative_ids)
        clearing = max(c.bid_cpm / 1000.0 - random.uniform(0, 0.002), 0.001)
        events.append(AdEvent(
            event_type=EventType.IMPRESSION,
            timestamp=ts.isoformat(),
            user_id=u["user_id"],
            campaign_id=c.campaign_id,
            advertiser_id=c.advertiser_id,
            creative_id=creative,
            site_domain=u["site_domain"],
            geo_country=u["geo_country"],
            device_type=u["device_type"],
            bid_price=c.bid_cpm / 1000.0,
            clearing_price=clearing,
            revenue=clearing,
        ))
        if random.random() < ctr_base * random.uniform(0.5, 1.8):
            events.append(AdEvent(
                event_type=EventType.CLICK,
                timestamp=ts.isoformat(),
                user_id=u["user_id"],
                campaign_id=c.campaign_id,
                advertiser_id=c.advertiser_id,
                creative_id=creative,
                site_domain=u["site_domain"],
                geo_country=u["geo_country"],
                device_type=u["device_type"],
            ))
            if random.random() < cvr_base * random.uniform(0.5, 2.0):
                events.append(AdEvent(
                    event_type=EventType.CONVERSION,
                    timestamp=ts.isoformat(),
                    user_id=u["user_id"],
                    campaign_id=c.campaign_id,
                    advertiser_id=c.advertiser_id,
                    creative_id=creative,
                    site_domain=u["site_domain"],
                    geo_country=u["geo_country"],
                    device_type=u["device_type"],
                    conversion_value=random.uniform(15, 220),
                ))
    return events


def advertiser_lookup() -> dict[str, str]:
    return dict(ADVERTISERS)
