"""Star schema records, subset of the production warehouse.

The full Redshift deployment has 32 fact tables and 128 dimensions; the
table-name lists at the bottom of this file enumerate the production
inventory. The dataclasses here are the subset the demo writes against.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class FactImpression:
    impression_id: str
    timestamp: datetime
    campaign_sk: int
    advertiser_sk: int
    creative_sk: int
    user_sk: int
    site_sk: int
    geo_sk: int
    device_sk: int
    bid_price: float
    clearing_price: float
    revenue: float
    auction_type: str  # 'first', 'second'


@dataclass
class FactClick:
    click_id: str
    timestamp: datetime
    impression_id: str
    campaign_sk: int
    user_sk: int
    creative_sk: int
    dwell_time_ms: int


@dataclass
class FactConversion:
    conversion_id: str
    timestamp: datetime
    user_sk: int
    campaign_sk: int
    attributed_impression_id: Optional[str]
    attributed_click_id: Optional[str]
    attribution_model: str  # last_touch, first_touch, linear, time_decay
    conversion_value: float
    conversion_type: str  # purchase, signup, app_install, lead


@dataclass
class DimCampaign:
    campaign_sk: int
    campaign_id: str
    advertiser_sk: int
    name: str
    objective: str  # awareness, consideration, conversion
    start_date: datetime
    end_date: Optional[datetime]
    status: str  # active, paused, completed
    is_current: bool = True


@dataclass
class DimUser:
    user_sk: int
    user_id: str
    first_seen: datetime
    age_bucket: str
    gender: str
    interests: list[str]
    lifetime_impressions: int = 0
    lifetime_clicks: int = 0
    lifetime_conversions: int = 0


# Schema-level constant: 32 fact tables and 128 dimension tables in production
FACT_TABLE_NAMES = [
    "fact_impression", "fact_click", "fact_conversion", "fact_bid_request",
    "fact_bid_response", "fact_viewability", "fact_video_completion",
    "fact_search_query", "fact_creative_render", "fact_video_quartile",
    "fact_install", "fact_revenue_event", "fact_audience_match",
    "fact_segment_membership", "fact_pacing_decision", "fact_budget_event",
    "fact_advertiser_payment", "fact_publisher_payout", "fact_floor_decision",
    "fact_targeting_match", "fact_attribution_path", "fact_user_journey",
    "fact_creative_quality_score", "fact_brand_safety_check",
    "fact_fraud_check", "fact_viewability_measurement", "fact_audio_event",
    "fact_ctv_event", "fact_dco_render", "fact_pmp_deal_event",
    "fact_header_bid", "fact_supply_path",
]
DIM_TABLE_NAMES = [
    "dim_campaign", "dim_advertiser", "dim_creative", "dim_user", "dim_site",
    "dim_geo", "dim_device", "dim_browser", "dim_os", "dim_carrier",
    # ... 118 more in production
]
