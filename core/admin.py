from django.contrib import admin

from .models import Payment, Task, Worker

admin.site.site_header = "AgenteKipu"
admin.site.site_title = "AgenteKipu"
admin.site.index_title = "Administración"


@admin.register(Worker)
class WorkerAdmin(admin.ModelAdmin):
    list_display = ("nombre", "direccion_stellar")
    search_fields = ("nombre", "direccion_stellar")


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ("titulo", "worker", "monto", "estado")
    list_filter = ("estado",)
    search_fields = ("titulo", "worker__nombre")


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("task", "monto", "estado", "tx_hash", "fecha")
    list_filter = ("estado",)
    search_fields = ("tx_hash", "task__titulo")
