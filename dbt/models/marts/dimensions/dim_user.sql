{{ config(materialized='table') }}

with imp as (
    select user_id,
           min(event_ts)            as first_seen,
           max(event_ts)            as last_seen,
           count(*)                 as lifetime_impressions
    from {{ ref('stg_impressions') }}
    group by 1
),
clk as (
    select user_id, count(*) as lifetime_clicks
    from {{ ref('stg_clicks') }} group by 1
),
conv as (
    select user_id,
           count(*)                       as lifetime_conversions,
           sum(conversion_value)::numeric as lifetime_value
    from {{ ref('stg_conversions') }} group by 1
)

select
    {{ dbt_utils.generate_surrogate_key(['imp.user_id']) }} as user_sk,
    imp.user_id,
    imp.first_seen,
    imp.last_seen,
    imp.lifetime_impressions,
    coalesce(clk.lifetime_clicks, 0)        as lifetime_clicks,
    coalesce(conv.lifetime_conversions, 0)  as lifetime_conversions,
    coalesce(conv.lifetime_value, 0)        as lifetime_value
from imp
left join clk  using (user_id)
left join conv using (user_id)
