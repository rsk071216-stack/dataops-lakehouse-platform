-- Bronze: typed and renamed 1:1 copy of the raw delivery. No rows are dropped
-- here; business rules live in silver so rejected rows stay explainable.
with source as (

    select * from {{ source('raw_tlc', 'green_trips') }}

),

renamed as (

    select
        cast(vendor_id as integer) as vendor_id,
        pickup_datetime as pickup_at,
        dropoff_datetime as dropoff_at,
        coalesce(store_and_fwd_flag = 'Y', false) as is_store_and_forward,
        cast(ratecode_id as integer) as rate_code_id,
        cast(pickup_location_id as integer) as pickup_zone_id,
        cast(dropoff_location_id as integer) as dropoff_zone_id,
        cast(passenger_count as integer) as passenger_count,
        cast(trip_distance as decimal(10, 2)) as trip_distance_mi,
        cast(fare_amount as decimal(12, 2)) as fare_amount,
        cast(extra as decimal(12, 2)) as extra_amount,
        cast(mta_tax as decimal(12, 2)) as mta_tax_amount,
        cast(tip_amount as decimal(12, 2)) as tip_amount,
        cast(tolls_amount as decimal(12, 2)) as tolls_amount,
        cast(improvement_surcharge as decimal(12, 2)) as improvement_surcharge_amount,
        cast(congestion_surcharge as decimal(12, 2)) as congestion_surcharge_amount,
        cast(total_amount as decimal(12, 2)) as total_amount,
        cast(payment_type as integer) as payment_type_code,
        cast(trip_type as integer) as trip_type_code,
        source_month,
        source_file,
        ingested_at,
        _dlt_load_id as load_id
    from source

)

select * from renamed
