{{ config(materialized='view') }}

select
    event_id              as conversion_id,
    cast(ts as timestamp) as event_ts,
    campaign_id,
    creative_id,
    user_id,
    coalesce(conversion_value, 0)::numeric as conversion_value
from {{ source('raw', 'fact_conversion') }}
where ts is not null
