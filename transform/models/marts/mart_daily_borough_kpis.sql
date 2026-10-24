-- Grain: one row per pickup date and pickup borough.
select
    pickup_date,
    pickup_borough,
    count(*) as trips,
    cast(sum(total_amount) as decimal(14, 2)) as gross_revenue,
    cast(sum(fare_amount) as decimal(14, 2)) as fare_revenue,
    cast(sum(tip_amount) as decimal(14, 2)) as tip_revenue,
    cast(avg(fare_amount) as decimal(10, 2)) as avg_fare,
    cast(avg(trip_distance_mi) as decimal(10, 2)) as avg_trip_distance_mi,
    cast(avg(trip_duration_min) as decimal(10, 2)) as avg_trip_duration_min,
    cast(avg(card_tip_rate) as decimal(8, 4)) as avg_card_tip_rate,
    cast(
        sum(case when is_airport_trip then 1 else 0 end) * 1.0 / count(*)
        as decimal(8, 4)
    ) as airport_trip_share
from {{ ref('fct_trips') }}
group by pickup_date, pickup_borough
