List
{% for line in text %} {{ line | truncate(50, True)}} 
{% endfor %}
