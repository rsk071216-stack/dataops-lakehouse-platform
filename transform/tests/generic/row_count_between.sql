{#- Volume guard rail: fails when a model's row count leaves the expected band.
    Catches truncated or duplicated deliveries that every row-level test misses. -#}
{% test row_count_between(model, min_rows, max_rows) %}

with counted as (

    select count(*) as row_count from {{ model }}

)

select row_count
from counted
where row_count < {{ min_rows }} or row_count > {{ max_rows }}

{% endtest %}
