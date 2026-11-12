from django import template

register = template.Library()


@register.filter
def mult(value):
    """1.0 → '1', 2.0 → '2', 0.5 → '½', 0.25 → '¼', 0 → '0'."""
    return {0.0: '0', 0.25: '¼', 0.5: '½', 1.0: '', 2.0: '2', 4.0: '4'}.get(value, str(value))


@register.filter
def mult_class(value):
    if value == 0:
        return 'eff-0'
    if value < 1:
        return 'eff-half'
    if value > 1:
        return 'eff-double'
    return ''


@register.filter
def percent(value, maximum):
    try:
        return min(100, round(float(value) / float(maximum) * 100))
    except (TypeError, ValueError, ZeroDivisionError):
        return 0


@register.filter
def stat_color(value):
    value = int(value or 0)
    if value < 50:
        return '#f34444'
    if value < 80:
        return '#ff7f0f'
    if value < 100:
        return '#ffdd57'
    if value < 120:
        return '#a0e515'
    return '#23cd5e'
