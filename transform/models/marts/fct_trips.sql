with trips as (

    select * from {{ ref('int_trips__cleaned') }}

),

zones as (

    select * from {{ ref('dim_zones') }}

)

select
    trips.trip_id,
    trips.vendor_id,
    trips.pickup_at,
    trips.dropoff_at,
    cast(trips.pickup_at as date) as pickup_date,
    cast(extract(hour from trips.pickup_at) as integer) as pickup_hour,
    trips.pickup_zone_id,
    trips.dropoff_zone_id,
    pickup_zone.borough as pickup_borough,
    dropoff_zone.borough as dropoff_borough,
    trips.passenger_count,
    trips.trip_distance_mi,
    trips.trip_duration_min,
    trips.fare_amount,
    trips.tip_amount,
    trips.tolls_amount,
    trips.total_amount,
    trips.payment_type_code,
    {{ payment_method('trips.payment_type_code') }} as payment_method,
    {{ trip_kind('trips.trip_type_code') }} as trip_kind,
    coalesce(pickup_zone.is_airport or dropoff_zone.is_airport, false) as is_airport_trip,
    -- Tips are only recorded electronically, so the tip rate is defined for card trips only.
    case
        when trips.payment_type_code = 1 and trips.fare_amount > 0
            then cast(trips.tip_amount / trips.fare_amount as decimal(8, 4))
    end as card_tip_rate
from trips
left join zones as pickup_zone
    on trips.pickup_zone_id = pickup_zone.zone_id
left join zones as dropoff_zone
    on trips.dropoff_zone_id = dropoff_zone.zone_id
