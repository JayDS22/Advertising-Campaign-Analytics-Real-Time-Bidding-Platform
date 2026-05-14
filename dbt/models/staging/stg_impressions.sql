{{ config(materialized='view') }}

with raw as (
    select
        event_id            as impression_id,
        cast(ts as timestamp) as event_ts,
        campaign_id,
        creative_id,
        user_id,
        geo_country,
        device_type,
        clearing_price,
        revenue
    from {{ source('raw', 'fact_impression') }}
)

select
    impression_id,
    event_ts,
    date_trunc('hour', event_ts)            as event_hour,
    date_trunc('day',  event_ts)            as event_day,
    campaign_id,
    creative_id,
    user_id,
    upper(geo_country)                      as geo_country,
    lower(device_type)                      as device_type,
    coalesce(clearing_price, 0)::numeric    as clearing_price,
    coalesce(revenue, 0)::numeric           as revenue
from raw
where event_ts is not null
