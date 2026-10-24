with source as (

    select * from {{ source('raw_tlc', 'taxi_zones') }}

)

select
    cast(location_id as integer) as zone_id,
    borough,
    zone as zone_name,
    service_zone,
    ingested_at
from source
