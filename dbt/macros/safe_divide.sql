{% macro safe_divide(numerator, denominator) %}
    case when {{ denominator }} = 0 or {{ denominator }} is null
         then 0
         else ({{ numerator }})::numeric / ({{ denominator }})
    end
{% endmacro %}
