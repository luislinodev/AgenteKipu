from django.contrib import admin
from django.utils.html import format_html

from .models import Operador, Payment, Punto, Recolector, Ruta

STELLAR_EXPERT_TX = "https://stellar.expert/explorer/testnet/tx/{}"
STELLAR_EXPERT_ACCOUNT = "https://stellar.expert/explorer/testnet/account/{}"

admin.site.site_header = "AgenteKipu"
admin.site.site_title = "AgenteKipu"
admin.site.index_title = "Administración"


def _acotar_a_operador(request, queryset, lookup):
    if request.user.is_superuser:
        return queryset
    return queryset.filter(**{lookup: request.user})


@admin.register(Operador)
class OperadorAdmin(admin.ModelAdmin):
    list_display = ("nombre", "user")
    search_fields = ("nombre", "user__username")


@admin.register(Recolector)
class RecolectorAdmin(admin.ModelAdmin):
    list_display = ("user", "wallet", "direccion_stellar")
    search_fields = ("nombre", "direccion_stellar", "user__username")
    autocomplete_fields = ("user",)

    def get_fields(self, request, obj=None):
        if obj:
            return ("user", "direccion_stellar", "wallet")
        return ("user", "direccion_stellar")

    def get_readonly_fields(self, request, obj=None):
        if obj:
            return ("wallet",)
        return ()

    @admin.display(description="Wallet")
    def wallet(self, recolector):
        if not recolector.direccion_stellar:
            return "—"
        url = STELLAR_EXPERT_ACCOUNT.format(recolector.direccion_stellar)
        return format_html(
            '<a href="{}" target="_blank" rel="noopener noreferrer">Ver en stellar.expert</a>',
            url,
        )


@admin.register(Punto)
class PuntoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "operador")
    search_fields = ("nombre", "operador__nombre")
    ordering = ("nombre",)

    def get_queryset(self, request):
        return _acotar_a_operador(
            request,
            super().get_queryset(request),
            "operador__user",
        )

    def get_fields(self, request, obj=None):
        if request.user.is_superuser:
            return ("operador", "nombre")
        return ("nombre",)

    def save_model(self, request, obj, form, change):
        if not request.user.is_superuser and not obj.operador_id:
            obj.operador = request.user.operador
        super().save_model(request, obj, form, change)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "operador" and not request.user.is_superuser:
            kwargs["queryset"] = Operador.objects.filter(user=request.user)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(Ruta)
class RutaAdmin(admin.ModelAdmin):
    list_display = ("punto", "recolector", "fecha", "monto", "estado")
    list_filter = ("fecha", "estado")
    search_fields = ("punto__nombre", "recolector__nombre", "nombre")
    autocomplete_fields = ("punto", "recolector")
    readonly_fields = ("estado",)

    def get_fields(self, request, obj=None):
        comunes = ("punto", "recolector", "monto", "fecha")
        if request.user.is_superuser:
            return ("operador",) + comunes
        return comunes

    def get_queryset(self, request):
        return _acotar_a_operador(
            request,
            super().get_queryset(request).select_related("punto", "recolector"),
            "operador__user",
        )

    def save_model(self, request, obj, form, change):
        if obj.punto_id:
            obj.operador = obj.punto.operador
        elif not request.user.is_superuser:
            obj.operador = request.user.operador
        super().save_model(request, obj, form, change)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if not request.user.is_superuser:
            if db_field.name == "punto":
                kwargs["queryset"] = Punto.objects.filter(operador__user=request.user)
            if db_field.name == "operador":
                kwargs["queryset"] = Operador.objects.filter(user=request.user)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("ruta", "monto", "estado", "transferencia", "fecha", "tx_hash")
    list_filter = ("estado",)
    search_fields = ("tx_hash", "ruta__punto__nombre")
    readonly_fields = ("transferencia",)

    @admin.display(description="Transferencia")
    def transferencia(self, payment):
        if not payment.tx_hash:
            return "—"
        url = STELLAR_EXPERT_TX.format(payment.tx_hash)
        return format_html(
            '<a href="{}" target="_blank" rel="noopener noreferrer">Ver en stellar.expert</a>',
            url,
        )

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
