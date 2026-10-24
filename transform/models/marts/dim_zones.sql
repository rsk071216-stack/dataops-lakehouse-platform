select
    zone_id,
    borough,
    zone_name,
    service_zone,
    coalesce(service_zone in ('Airports', 'EWR'), false) as is_airport
from {{ ref('stg_tlc__taxi_zones') }}
