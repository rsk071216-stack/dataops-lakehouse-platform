-- Quarantine: trips that failed a business rule, kept for the data quality report
-- and for upstream feedback instead of being dropped.
select
    trip_id,
    rejection_reason,
    vendor_id,
    pickup_at,
    dropoff_at,
    pickup_zone_id,
    trip_distance_mi,
    trip_duration_min,
    fare_amount,
    total_amount,
    source_month,
    source_file,
    load_id
from {{ ref('int_trips__validated') }}
where rejection_reason is not null
