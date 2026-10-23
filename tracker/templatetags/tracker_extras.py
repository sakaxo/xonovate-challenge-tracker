from django import template

from ..services import CURRENCY_SYMBOL, money

register = template.Library()


@register.filter
def cedi(value):
    return f"{CURRENCY_SYMBOL}{money(value):,.2f}"


@register.filter
def pct(value):
    if value is None:
        return "—"
    return f"{value:.1f}%"


@register.filter
def progress_width(value):
    if value is None:
        return 0
    return min(float(value), 100)
