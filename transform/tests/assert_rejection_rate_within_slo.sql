-- Data quality SLO: no more than 15% of a delivery may be quarantined.
-- A higher rate means the upstream feed broke, not that the data got noisier.
{{ config(severity='error') }}

with rates as (

    select
        source_month,
        sum(case when rejection_reason is not null then 1 else 0 end) * 1.0 / count(*)
            as rejection_rate
    from {{ ref('int_trips__validated') }}
    group by source_month

)

select *
from rates
where rejection_rate > {{ var('max_rejection_rate', 0.15) }}
