from django.contrib.auth import views as auth_views
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
    path("tareas/<int:task_id>/pago/", views.detalle_pago, name="detalle_pago"),
    path(
        "confirmar/<str:token>/",
        views.confirmar_punto,
        name="confirmar_punto",
    ),
    path(
        "cuentas/entrar/",
        auth_views.LoginView.as_view(template_name="core/login.html"),
        name="login",
    ),
    path(
        "cuentas/salir/",
        auth_views.LogoutView.as_view(next_page="login"),
        name="logout",
    ),
    path("recolector/", views.panel_recolector, name="panel_recolector"),
    path(
        "recolector/puntos/<int:punto_id>/foto/",
        views.subir_foto,
        name="subir_foto",
    ),
    path("inicio/", views.despues_de_entrar, name="despues_de_entrar"),
    path("operador/", views.panel_operador, name="panel_operador"),
    path(
        "operador/rutas/<int:ruta_id>/",
        views.detalle_ruta_operador,
        name="detalle_ruta_operador",
    ),
    path(
        "operador/puntos/<int:punto_id>/",
        views.detalle_punto_operador,
        name="detalle_punto_operador",
    ),
]
