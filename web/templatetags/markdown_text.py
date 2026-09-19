import re

from django import template

register = template.Library()


@register.filter
def markdown_inline(value):
    text = " ".join(str(value or "").split())
    return re.sub(r"([\\`*_{}\[\]()<>#!|~&])", r"\\\1", text)
