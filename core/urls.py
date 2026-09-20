from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("tareas/nueva/", views.crear_tarea, name="crear_tarea"),
    path(
        "tareas/<int:task_id>/completar/",
        views.marcar_completada,
        name="marcar_completada",
    ),
    path(
        "tareas/<int:task_id>/verificar/",
        views.marcar_verificada,
        name="marcar_verificada",
    ),
    path("tareas/<int:task_id>/pago/", views.detalle_pago, name="detalle_pago"),
]
