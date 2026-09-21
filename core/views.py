from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format

from .gemini_check import chequear_consistencia
from .models import Operador, Punto, Recolector, Ruta
from .signals import intentar_pago_si_corresponde


def dashboard(request):
    if request.user.is_authenticated:
        return redirect("despues_de_entrar")
    return render(request, "core/dashboard.html")


def _puede_confirmar(punto):
    return punto.confirmacion is None and punto.estado != Punto.Estado.PAGADO


def _puede_subir_foto(punto):
    # Una sola subida dispara Gemini y el token. Reemplazar la foto
    # dejaría reintentar el chequeo de consistencia.
    # No leer token_confirmacion: en el panel del recolector está en defer.
    if punto.foto:
        return False
    if punto.confirmacion or punto.estado == Punto.Estado.PAGADO:
        return False
    return True


def _texto_gemini(punto):
    if punto.gemini_error:
        return "error"
    if punto.gemini_consistente is True:
        return f"consistente ({punto.gemini_cantidad})"
    if punto.gemini_consistente is False:
        return f"inconsistente ({punto.gemini_cantidad})"
    return "—"


def confirmar_punto(request, token):
    punto = get_object_or_404(Punto, token_confirmacion=token)
    template = "core/confirmar_punto.html"

    if request.method != "POST":
        return render(
            request,
            template,
            {
                "punto": punto,
                "formulario_abierto": _puede_confirmar(punto),
            },
        )

    respuesta = request.POST.get("confirmacion", "").strip()
    if respuesta not in (Punto.Confirmacion.SI, Punto.Confirmacion.NO):
        return render(
            request,
            template,
            {
                "punto": punto,
                "formulario_abierto": _puede_confirmar(punto),
                "error": "Elegí Sí o No.",
            },
        )

    filas = (
        Punto.objects.filter(
            pk=punto.pk,
            confirmacion__isnull=True,
        )
        .exclude(estado=Punto.Estado.PAGADO)
        .update(
            confirmacion=respuesta,
            confirmado_en=timezone.now(),
        )
    )
    punto = Punto.objects.get(pk=punto.pk)

    if filas == 0:
        return render(
            request,
            template,
            {
                "punto": punto,
                "formulario_abierto": False,
            },
        )

    intentar_pago_si_corresponde(sender=Punto, instance=punto)
    punto = Punto.objects.get(pk=punto.pk)
    return render(
        request,
        template,
        {
            "punto": punto,
            "formulario_abierto": False,
            "respuesta_registrada": True,
        },
    )


def _recolector_actual(request):
    recolector = Recolector.objects.filter(user=request.user).first()
    if recolector is None:
        raise Http404()
    return recolector


def _operador_actual(request):
    operador = Operador.objects.filter(user=request.user).first()
    if operador is None:
        raise Http404()
    return operador


def _url_confirmacion(request, punto):
    if not punto.token_confirmacion:
        return ""
    return request.build_absolute_uri(
        reverse("confirmar_punto", kwargs={"token": punto.token_confirmacion})
    )


def _json_punto_operador(request, punto):
    return {
        "id": punto.pk,
        "nombre_local": punto.nombre_local,
        "detalle_url": reverse("detalle_punto_operador", args=[punto.pk]),
        "estado": punto.estado,
        "estado_display": punto.get_estado_display(),
        "cantidad_baldes": punto.cantidad_baldes,
        "gemini": _texto_gemini(punto),
        "confirmacion_display": punto.get_confirmacion_display() or "—",
        "motivo_no_pago": punto.motivo_no_pago or "",
        "url_confirmacion": _url_confirmacion(request, punto),
    }


def _json_punto_recolector(punto):
    puede_subir = _puede_subir_foto(punto)
    return {
        "id": punto.pk,
        "nombre_local": punto.nombre_local,
        "ruta": punto.ruta.nombre,
        "estado": punto.estado,
        "estado_display": punto.get_estado_display(),
        "tiene_foto": bool(punto.foto),
        "puede_subir": puede_subir,
        "subir_url": reverse("subir_foto", args=[punto.pk]) if puede_subir else "",
    }


@login_required
def despues_de_entrar(request):
    if Operador.objects.filter(user=request.user).exists():
        return redirect("panel_operador")
    if Recolector.objects.filter(user=request.user).exists():
        return redirect("panel_recolector")
    raise Http404()


@login_required
def panel_recolector(request):
    recolector = _recolector_actual(request)
    puntos = (
        Punto.objects.filter(ruta__recolector=recolector)
        .select_related("ruta")
        # defer no es control de acceso: el template no recibe el token.
        .defer("token_confirmacion")
        .order_by("ruta__fecha", "id")
    )
    return render(
        request,
        "core/panel_recolector.html",
        {"recolector": recolector, "puntos": puntos},
    )


@login_required
def subir_foto(request, punto_id):
    recolector = _recolector_actual(request)
    # defer no es ACL; el 404 sale de ruta__recolector y el template no usa el token.
    punto = get_object_or_404(
        Punto.objects.select_related("ruta").defer("token_confirmacion"),
        pk=punto_id,
        ruta__recolector=recolector,
    )
    if not _puede_subir_foto(punto):
        messages.error(
            request,
            "Este punto ya no admite una foto nueva.",
        )
        return redirect("panel_recolector")

    if request.method != "POST":
        return render(request, "core/subir_foto.html", {"punto": punto})

    foto = request.FILES.get("foto")
    cantidad_raw = request.POST.get("cantidad_baldes", "").strip()
    errores = []
    if not foto:
        errores.append("La foto es obligatoria.")
    try:
        cantidad = int(cantidad_raw)
        if cantidad < 0:
            errores.append("La cantidad de baldes no puede ser negativa.")
    except (TypeError, ValueError):
        cantidad = None
        errores.append("Indicá cuántos baldes recogiste.")

    if errores:
        for error in errores:
            messages.error(request, error)
        return render(request, "core/subir_foto.html", {"punto": punto})

    punto.foto = foto
    punto.cantidad_baldes = cantidad
    punto.save()
    punto.asegurar_token()

    punto.foto.open("rb")
    try:
        foto_bytes = punto.foto.read()
    finally:
        punto.foto.close()
    mime_type = getattr(foto, "content_type", "") or "image/jpeg"

    resultado = chequear_consistencia(
        foto_bytes=foto_bytes,
        mime_type=mime_type,
        cantidad_reportada=cantidad,
    )
    punto.gemini_cantidad = resultado.cantidad
    punto.gemini_consistente = resultado.consistente
    punto.gemini_respuesta = resultado.respuesta
    punto.gemini_error = resultado.error
    punto.save(
        update_fields=[
            "gemini_cantidad",
            "gemini_consistente",
            "gemini_respuesta",
            "gemini_error",
        ]
    )
    messages.success(request, f"Foto recibida para «{punto.nombre_local}».")
    return redirect("panel_recolector")


@login_required
def panel_operador(request):
    operador = _operador_actual(request)
    rutas = (
        Ruta.objects.filter(operador__user=request.user)
        .select_related("recolector")
        .prefetch_related("puntos")
        .order_by("-fecha", "-id")
    )
    return render(
        request,
        "core/panel_operador.html",
        {"operador": operador, "rutas": rutas},
    )


@login_required
def detalle_ruta_operador(request, ruta_id):
    operador = _operador_actual(request)
    ruta = get_object_or_404(
        Ruta.objects.select_related("recolector").prefetch_related("puntos"),
        pk=ruta_id,
        operador__user=request.user,
    )
    filas = [
        {
            "punto": punto,
            "url_confirmacion": _url_confirmacion(request, punto),
            "texto_gemini": _texto_gemini(punto),
        }
        for punto in ruta.puntos.all()
    ]
    return render(
        request,
        "core/detalle_ruta_operador.html",
        {"operador": operador, "ruta": ruta, "filas": filas},
    )


@login_required
def detalle_punto_operador(request, punto_id):
    operador = _operador_actual(request)
    punto = get_object_or_404(
        Punto.objects.select_related("ruta__recolector"),
        pk=punto_id,
        ruta__operador__user=request.user,
    )
    return render(
        request,
        "core/detalle_punto_operador.html",
        {
            "operador": operador,
            "punto": punto,
            "url_confirmacion": _url_confirmacion(request, punto),
            "texto_gemini": _texto_gemini(punto),
        },
    )


@login_required
def estado_panel_operador(request):
    _operador_actual(request)
    rutas = (
        Ruta.objects.filter(operador__user=request.user)
        .select_related("recolector")
        .prefetch_related("puntos")
        .order_by("-fecha", "-id")
    )
    return JsonResponse(
        {
            "rutas": [
                {
                    "id": ruta.pk,
                    "nombre": ruta.nombre,
                    "fecha": date_format(ruta.fecha),
                    "recolector": ruta.recolector.nombre,
                    "puntos": len(ruta.puntos.all()),
                    "url": reverse("detalle_ruta_operador", args=[ruta.pk]),
                }
                for ruta in rutas
            ]
        }
    )


@login_required
def estado_ruta_operador(request, ruta_id):
    _operador_actual(request)
    ruta = get_object_or_404(
        Ruta.objects.prefetch_related("puntos"),
        pk=ruta_id,
        operador__user=request.user,
    )
    return JsonResponse(
        {
            "puntos": [
                _json_punto_operador(request, punto) for punto in ruta.puntos.all()
            ]
        }
    )


@login_required
def estado_punto_operador(request, punto_id):
    _operador_actual(request)
    punto = get_object_or_404(
        Punto,
        pk=punto_id,
        ruta__operador__user=request.user,
    )
    return JsonResponse(_json_punto_operador(request, punto))


@login_required
def estado_panel_recolector(request):
    recolector = _recolector_actual(request)
    puntos = (
        Punto.objects.filter(ruta__recolector=recolector)
        .select_related("ruta")
        .defer("token_confirmacion")
        .order_by("ruta__fecha", "id")
    )
    return JsonResponse(
        {"puntos": [_json_punto_recolector(punto) for punto in puntos]}
    )


def estado_confirmar_punto(request, token):
    punto = get_object_or_404(Punto, token_confirmacion=token)
    return JsonResponse(
        {
            "formulario_abierto": _puede_confirmar(punto),
            "confirmacion_display": punto.get_confirmacion_display() or "",
        }
    )
