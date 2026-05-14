{{ config(materialized='table') }}

-- Campaign dimension. Production hydrates this from a 30-minute snapshot
-- of the campaign-management OLTP store via an upstream Airflow task,
-- materialized as Type-2 SCD with effective_from / effective_to / is_current.

with src as (
    select distinct
        campaign_id,
        first_value(advertiser_id) over (partition by campaign_id order by event_ts) as advertiser_id
    from {{ ref('stg_impressions') }}
)
select
    {{ dbt_utils.generate_surrogate_key(['campaign_id']) }} as campaign_sk,
    campaign_id,
    advertiser_id,
    'active' as status,
    current_timestamp as effective_from,
    null::timestamp   as effective_to,
    true              as is_current
from src
