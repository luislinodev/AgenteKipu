from django.utils import timezone


def fecha_hora(valor):
    """21/09/2026 - 03:15:43 pm, en la zona horaria del proyecto."""
    if not valor:
        return ""
    if timezone.is_aware(valor):
        valor = timezone.localtime(valor)
    sufijo = "am" if valor.hour < 12 else "pm"
    return f"{valor:%d/%m/%Y} - {valor:%I:%M:%S} {sufijo}"
