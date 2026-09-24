from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path(
        "confirmar/<str:token>/",
        views.confirmar_punto,
        name="confirmar_punto",
    ),
    path(
        "confirmar/<str:token>/estado/",
        views.estado_confirmar_punto,
        name="estado_confirmar_punto",
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
        "recolector/estado/",
        views.estado_panel_recolector,
        name="estado_panel_recolector",
    ),
    path("recolector/pagos/", views.pagos_recolector, name="pagos_recolector"),
    path(
        "recolector/pagos/estado/",
        views.estado_pagos_recolector,
        name="estado_pagos_recolector",
    ),
    path(
        "recolector/rutas/<int:ruta_id>/",
        views.detalle_ruta_recolector,
        name="detalle_ruta_recolector",
    ),
    path(
        "recolector/rutas/<int:ruta_id>/foto/",
        views.subir_foto,
        name="subir_foto",
    ),
    path("inicio/", views.despues_de_entrar, name="despues_de_entrar"),
    path("operador/", views.panel_operador, name="panel_operador"),
    path("operador/puntos/", views.puntos_operador, name="puntos_operador"),
    path(
        "operador/puntos/nuevo/",
        views.crear_punto_operador,
        name="crear_punto_operador",
    ),
    path(
        "operador/rutas/nueva/",
        views.crear_ruta_operador,
        name="crear_ruta_operador",
    ),
    path(
        "operador/estado/",
        views.estado_panel_operador,
        name="estado_panel_operador",
    ),
    path("operador/pagos/", views.pagos_operador, name="pagos_operador"),
    path(
        "operador/pagos/estado/",
        views.estado_pagos_operador,
        name="estado_pagos_operador",
    ),
    path(
        "operador/rutas/<int:ruta_id>/",
        views.detalle_ruta_operador,
        name="detalle_ruta_operador",
    ),
    path(
        "operador/rutas/<int:ruta_id>/proceder/",
        views.proceder_pago_operador,
        name="proceder_pago_operador",
    ),
    path(
        "operador/rutas/<int:ruta_id>/estado/",
        views.estado_ruta_operador,
        name="estado_ruta_operador",
    ),
]
