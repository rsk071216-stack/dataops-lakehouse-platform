{#- Human-readable labels for TLC code lists, kept in one place for every model. -#}

{% macro payment_method(code_column) -%}
    case {{ code_column }}
        when 0 then 'flex_fare'
        when 1 then 'card'
        when 2 then 'cash'
        when 3 then 'no_charge'
        when 4 then 'dispute'
        when 6 then 'voided'
        else 'unknown'
    end
{%- endmacro %}

{% macro trip_kind(code_column) -%}
    case {{ code_column }}
        when 1 then 'street_hail'
        when 2 then 'dispatch'
        else 'unknown'
    end
{%- endmacro %}
