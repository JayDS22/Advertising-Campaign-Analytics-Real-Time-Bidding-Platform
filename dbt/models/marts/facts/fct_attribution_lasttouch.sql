{{ config(materialized='incremental', unique_key='conversion_id') }}

-- Last-touch attribution with a configurable lookback (attribution_window_days).
-- Strategy: pick the most recent click before the conversion timestamp on the
-- same (user, campaign) tuple. If no click exists, fall back to the most
-- recent impression (view-through credit).

with conv as (
    select * from {{ ref('stg_conversions') }}
),
clicks as (
    select user_id, campaign_id, click_id, event_ts as click_ts
    from {{ ref('stg_clicks') }}
),
imps as (
    select user_id, campaign_id, impression_id, event_ts as imp_ts
    from {{ ref('stg_impressions') }}
),
joined_clicks as (
    select c.conversion_id, c.user_id, c.campaign_id, c.event_ts,
           cl.click_id, cl.click_ts,
           row_number() over (partition by c.conversion_id
                              order by cl.click_ts desc) as rn
    from conv c
    left join clicks cl
      on cl.user_id = c.user_id
     and cl.campaign_id = c.campaign_id
     and cl.click_ts <= c.event_ts
     and cl.click_ts >= c.event_ts - interval '{{ var("attribution_window_days") }} days'
),
last_click as (
    select * from joined_clicks where rn = 1
),
joined_imps as (
    select c.conversion_id, im.impression_id, im.imp_ts,
           row_number() over (partition by c.conversion_id
                              order by im.imp_ts desc) as rn
    from conv c
    left join imps im
      on im.user_id = c.user_id
     and im.campaign_id = c.campaign_id
     and im.imp_ts <= c.event_ts
     and im.imp_ts >= c.event_ts - interval '{{ var("attribution_window_days") }} days'
),
last_imp as (
    select * from joined_imps where rn = 1
)

select
    c.conversion_id,
    c.event_ts,
    c.user_id,
    c.campaign_id,
    c.conversion_value,
    lc.click_id          as attributed_click_id,
    li.impression_id     as attributed_impression_id,
    case when lc.click_id is not null then 'click'
         when li.impression_id is not null then 'view_through'
         else 'unattributed' end                          as attribution_type,
    'last_touch'                                          as attribution_model
from conv c
left join last_click lc on lc.conversion_id = c.conversion_id
left join last_imp   li on li.conversion_id = c.conversion_id
