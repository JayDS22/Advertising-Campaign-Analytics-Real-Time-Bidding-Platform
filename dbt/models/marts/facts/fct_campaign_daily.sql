{{ config(
    materialized='incremental',
    unique_key=['event_day', 'campaign_id'],
    incremental_strategy='delete+insert',
    sort=['event_day', 'campaign_id'],
    dist='campaign_id'
) }}

with imp as (
    select event_day, campaign_id,
           count(*)              as impressions,
           sum(revenue)          as ad_revenue,
           sum(clearing_price)   as ad_spend
    from {{ ref('stg_impressions') }}
    {% if is_incremental() %}
      where event_day >= (select coalesce(max(event_day), '1900-01-01') from {{ this }})
    {% endif %}
    group by 1, 2
),
clk as (
    select date_trunc('day', event_ts) as event_day,
           campaign_id, count(*) as clicks
    from {{ ref('stg_clicks') }}
    group by 1, 2
),
conv as (
    select date_trunc('day', event_ts) as event_day,
           campaign_id,
           count(*)               as conversions,
           sum(conversion_value)  as conversion_value
    from {{ ref('stg_conversions') }}
    group by 1, 2
)

select
    imp.event_day,
    imp.campaign_id,
    imp.impressions,
    coalesce(clk.clicks, 0)             as clicks,
    coalesce(conv.conversions, 0)       as conversions,
    coalesce(conv.conversion_value, 0)  as conversion_value,
    imp.ad_spend,
    imp.ad_revenue,
    case when imp.impressions > 0
         then coalesce(clk.clicks, 0)::numeric / imp.impressions
         else 0 end                                 as ctr,
    case when coalesce(clk.clicks, 0) > 0
         then coalesce(conv.conversions, 0)::numeric / clk.clicks
         else 0 end                                 as cvr,
    case when imp.ad_spend > 0
         then conv.conversion_value::numeric / imp.ad_spend
         else 0 end                                 as roas,
    case when coalesce(conv.conversions, 0) > 0
         then imp.ad_spend / conv.conversions
         else 0 end                                 as cpa,
    (imp.ad_spend / nullif(imp.impressions, 0)) * 1000 as cpm,
    current_timestamp                              as _loaded_at
from imp
left join clk  using (event_day, campaign_id)
left join conv using (event_day, campaign_id)
