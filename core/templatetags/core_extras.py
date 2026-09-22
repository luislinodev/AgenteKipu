from django import template

from core.formato import fecha_hora

register = template.Library()


@register.filter
def fecha_hora_display(valor):
    return fecha_hora(valor) or "—"
