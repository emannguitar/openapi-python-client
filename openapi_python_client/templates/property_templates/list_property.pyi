{% macro construct(property, source) %}
{% set inner_property = property.inner_property %}
{% if inner_property.template %}
{% set inner_source = inner_property.python_name + "_data" %}
{{ property.python_name }} = []
{% if property.required %}
for {{ inner_source }} in ({{ source }}):
{% else %}
for {{ inner_source }} in ({{ source }} or []):
{% endif %}
    {% from "property_templates/" + inner_property.template import construct %}
    {{ construct(inner_property, inner_source) | indent(4) }}
    {{ property.python_name }}.append({{ inner_property.python_name }})
{% else %}
{{ property.python_name }} = {{ source }}
{% endif %}
{% endmacro %}

{% macro _transform(property, source, destination) %}
{% set inner_property = property.inner_property %}
{% if inner_property.template %}
{% set inner_source = inner_property.python_name + "_data" %}
{{ destination }} = []
for {{ inner_source }} in {{ source }}:
    {% from "property_templates/" + inner_property.template import transform %}
    {{ transform(inner_property, inner_source, inner_property.python_name) | indent(4) }}
    {{ destination }}.append({{ inner_property.python_name }})
{% else %}
{{ destination }} = {{ source }}
{% endif %}
{% endmacro %}


{% macro transform(property, source, destination) %}
{% set inner_property = property.inner_property %}
{% if property.required %}
{% if property.nullable %}
if {{ source }} is None:
    {{ destination }} = None
else:
    {{ _transform(property, source, destination) | indent(4) }}
{% else %}
{{ _transform(property, source, destination) }}
{% endif %}
{% else %}
{{ destination }}: Union[Unset, List[Any]] = UNSET
if not isinstance({{ source }}, Unset):
{% if property.nullable %}
    if {{ source }} is None:
        {{ destination }} = None
    else:
        {{ _transform(property, source, destination) | indent(4)}}
{% else %}
    {{ _transform(property, source, destination) | indent(4)}}
{% endif %}
{% endif %}


{% endmacro %}
