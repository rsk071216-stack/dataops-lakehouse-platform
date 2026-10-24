-- Grain: one row per pickup zone, day type (weekday/weekend) and hour of day.
-- Feeds driver supply planning: where and when to position vehicles.
-- Zones 264 (Unknown) and 265 (Outside of NYC) cannot be staffed, so they are
-- excluded from planning (they remain in fct_trips for revenue reporting).
with trips as (

    select
        pickup_zone_id,
        pickup_date,
        pickup_hour,
        fare_amount,
        case
            when extract(isodow from pickup_at) in (6, 7) then 'weekend'
            else 'weekday'
        end as day_type
    from {{ ref('fct_trips') }}
    where pickup_zone_id not in (264, 265)

)

select
    trips.pickup_zone_id,
    zones.zone_name as pickup_zone_name,
    zones.borough as pickup_borough,
    trips.day_type,
    trips.pickup_hour,
    count(*) as trips,
    count(distinct trips.pickup_date) as active_days,
    cast(count(*) * 1.0 / count(distinct trips.pickup_date) as decimal(10, 2))
        as avg_trips_per_active_day,
    cast(avg(trips.fare_amount) as decimal(10, 2)) as avg_fare
from trips
left join {{ ref('dim_zones') }} as zones
    on trips.pickup_zone_id = zones.zone_id
group by
    trips.pickup_zone_id,
    zones.zone_name,
    zones.borough,
    trips.day_type,
    trips.pickup_hour
