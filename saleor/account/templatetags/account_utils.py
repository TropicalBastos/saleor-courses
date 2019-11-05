from django import template
from django.utils.translation import pgettext
from django.templatetags.static import static
from django.template.defaultfilters import safe, truncatechars

register = template.Library()


@register.filter()
def safe_truncate(string, arg):
    return truncatechars(safe(string), arg)