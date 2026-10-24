select * from {{ ref('int_trips__validated') }}
where rejection_reason is null
