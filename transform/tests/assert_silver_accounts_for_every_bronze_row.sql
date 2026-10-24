-- Every bronze trip must end up either in the clean set or in quarantine.
-- A mismatch means a filter or join silently dropped or duplicated rows.
with counts as (

    select
        (select count(*) from {{ ref('stg_tlc__green_trips') }}) as bronze_rows,
        (select count(*) from {{ ref('int_trips__cleaned') }}) as clean_rows,
        (select count(*) from {{ ref('int_trips__rejected') }}) as rejected_rows

)

select *
from counts
where bronze_rows != clean_rows + rejected_rows
