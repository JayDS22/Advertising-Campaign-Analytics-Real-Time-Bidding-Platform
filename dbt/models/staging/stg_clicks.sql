{{ config(materialized='view') }}

select
    event_id              as click_id,
    cast(ts as timestamp) as event_ts,
    campaign_id,
    creative_id,
    user_id,
    upper(geo_country)    as geo_country,
    lower(device_type)    as device_type
from {{ source('raw', 'fact_click') }}
where ts is not null
