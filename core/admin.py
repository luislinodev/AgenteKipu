from django.contrib import admin

from .models import Operador, Payment, Punto, Recolector, Ruta, Task, Worker

admin.site.site_header = "AgenteKipu"
admin.site.site_title = "AgenteKipu"
admin.site.index_title = "Administración"


def _acotar_a_operador(request, queryset, lookup):
    if request.user.is_superuser:
        return queryset
    return queryset.filter(**{lookup: request.user})


@admin.register(Worker)
class WorkerAdmin(admin.ModelAdmin):
    list_display = ("nombre", "direccion_stellar")
    search_fields = ("nombre", "direccion_stellar")


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ("titulo", "worker", "monto", "estado")
    list_filter = ("estado",)
    search_fields = ("titulo", "worker__nombre")


@admin.register(Operador)
class OperadorAdmin(admin.ModelAdmin):
    list_display = ("nombre", "user")
    search_fields = ("nombre", "user__username")


@admin.register(Recolector)
class RecolectorAdmin(admin.ModelAdmin):
    list_display = ("nombre", "direccion_stellar", "user")
    search_fields = ("nombre", "direccion_stellar", "user__username")


@admin.register(Ruta)
class RutaAdmin(admin.ModelAdmin):
    list_display = ("nombre", "fecha", "operador", "recolector")
    list_filter = ("fecha",)
    search_fields = ("nombre", "operador__nombre", "recolector__nombre")


@admin.register(Punto)
class PuntoAdmin(admin.ModelAdmin):
    list_display = (
        "nombre_local",
        "ruta",
        "monto",
        "estado",
        "confirmacion",
        "gemini_consistente",
        "motivo_no_pago",
    )
    list_filter = ("estado", "confirmacion", "gemini_consistente")
    search_fields = ("nombre_local", "ruta__nombre")

    def get_queryset(self, request):
        return _acotar_a_operador(
            request,
            super().get_queryset(request),
            "ruta__operador__user",
        )

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "ruta" and not request.user.is_superuser:
            kwargs["queryset"] = Ruta.objects.filter(operador__user=request.user)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("punto", "monto", "estado", "tx_hash", "fecha")
    list_filter = ("estado",)
    search_fields = ("tx_hash", "punto__nombre_local")

    def get_queryset(self, request):
        return _acotar_a_operador(
            request,
            super().get_queryset(request),
            "punto__ruta__operador__user",
        )

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "punto" and not request.user.is_superuser:
            kwargs["queryset"] = Punto.objects.filter(
                ruta__operador__user=request.user
            )
        return super().formfield_for_foreignkey(db_field, request, **kwargs)
