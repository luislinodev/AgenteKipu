from django import forms

from .models import Punto, Recolector, Ruta


class PuntoOperadorForm(forms.ModelForm):
    class Meta:
        model = Punto
        fields = ("nombre", "cantidad_promedio", "comision_por_balde")
        labels = {
            "nombre": "Nombre",
            "cantidad_promedio": "Cantidad promedio",
            "comision_por_balde": "Comisión por balde",
        }


class RutaOperadorForm(forms.ModelForm):
    class Meta:
        model = Ruta
        fields = ("punto", "recolector", "monto", "fecha")
        labels = {
            "punto": "Punto de recojo",
            "recolector": "Recolector",
            "monto": "Monto (XLM)",
            "fecha": "Fecha",
        }
        widgets = {
            "fecha": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, operador, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.operador = operador
        self.fields["punto"].queryset = Punto.objects.filter(operador=operador)
        self.fields["recolector"].queryset = Recolector.objects.order_by("nombre")
        self.fields["punto"].empty_label = "Elegí un punto"
        self.fields["recolector"].empty_label = "Elegí un recolector"
