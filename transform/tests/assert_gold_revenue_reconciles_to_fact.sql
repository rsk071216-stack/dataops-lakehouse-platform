-- The KPI mart must report exactly the revenue held in the trip fact table.
-- Guards against fan-out joins and filters added to the mart later.
with mart as (

    select coalesce(sum(gross_revenue), 0) as revenue from {{ ref('mart_daily_borough_kpis') }}

),

fact as (

    select coalesce(sum(total_amount), 0) as revenue from {{ ref('fct_trips') }}

)

select
    mart.revenue as mart_revenue,
    fact.revenue as fact_revenue
from mart
cross join fact
where abs(mart.revenue - fact.revenue) > 0.01
