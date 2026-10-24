-- Silver: every bronze trip with a deterministic key and the first business rule
-- it violates (null when the trip is valid). Downstream models split this into
-- clean trips and a quarantine table, so no row ever disappears silently.
{% set natural_key = [
    'vendor_id', 'pickup_at', 'dropoff_at', 'pickup_zone_id',
    'dropoff_zone_id', 'trip_distance_mi', 'total_amount'
] %}

with trips as (

    select * from {{ ref('stg_tlc__green_trips') }}

),

keyed as (

    select
        *,
        {{ dbt_utils.generate_surrogate_key(natural_key) }} as trip_id,  -- noqa: LT05
        cast(source_month || '-01' as date) as source_month_start,
        cast(
            {{ dbt.datediff('pickup_at', 'dropoff_at', 'second') }} / 60.0  -- noqa: LT05
            as decimal(10, 2)
        ) as trip_duration_min
    from trips

),

ranked as (

    select
        *,
        row_number() over (
            partition by trip_id
            order by load_id, source_file
        ) as duplicate_rank
    from keyed

)

select
    trip_id,
    vendor_id,
    pickup_at,
    dropoff_at,
    is_store_and_forward,
    rate_code_id,
    pickup_zone_id,
    dropoff_zone_id,
    passenger_count,
    trip_distance_mi,
    trip_duration_min,
    fare_amount,
    extra_amount,
    mta_tax_amount,
    tip_amount,
    tolls_amount,
    improvement_surcharge_amount,
    congestion_surcharge_amount,
    total_amount,
    payment_type_code,
    trip_type_code,
    source_month,
    source_file,
    load_id,
    case
        when pickup_at is null or dropoff_at is null then 'missing_timestamp'
        when duplicate_rank > 1 then 'duplicate_record'
        when
            pickup_at < source_month_start
            or pickup_at >= {{ dbt.dateadd('month', 1, 'source_month_start') }}
            then 'outside_source_month'
        when dropoff_at <= pickup_at then 'non_positive_duration'
        when trip_duration_min > 360 then 'implausible_duration'
        when trip_distance_mi <= 0 then 'zero_distance'
        when trip_distance_mi > 100 then 'implausible_distance'
        when fare_amount < 0 or total_amount < 0 then 'negative_amount'
    end as rejection_reason
from ranked
