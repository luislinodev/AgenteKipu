from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import number_format

from .formato import fecha_hora
from .forms import PuntoOperadorForm, RutaOperadorForm
from .gemini_check import chequear_consistencia
from .models import Operador, Payment, Punto, Recolector, Ruta
from .signals import intentar_pago_si_corresponde
from .stellar_agent import consultar_saldo_xlm, direccion_cuenta_pagadora

STELLAR_EXPERT_TX = "https://stellar.expert/explorer/testnet/tx/{}"
STELLAR_EXPERT_ACCOUNT = "https://stellar.expert/explorer/testnet/account/{}"


def dashboard(request):
    if request.user.is_authenticated:
        return redirect("despues_de_entrar")
    return render(request, "core/dashboard.html")


def _puede_confirmar(ruta):
    return ruta.confirmacion is None and ruta.estado != Ruta.Estado.PAGADO


def _puede_subir_foto(ruta):
    if ruta.foto:
        return False
    if ruta.confirmacion or ruta.estado == Ruta.Estado.PAGADO:
        return False
    return True


def _pago_de(ruta):
    try:
        return ruta.payment
    except Payment.DoesNotExist:
        return None


def _comision_pagada_display(ruta):
    pago = _pago_de(ruta)
    if pago is None:
        return ""
    return f"{number_format(pago.comision, decimal_pos=7)} XLM"


def _texto_gemini(ruta):
    if ruta.gemini_error:
        return "error"
    if ruta.gemini_consistente is True:
        return f"consistente ({ruta.gemini_cantidad})"
    if ruta.gemini_consistente is False:
        return f"inconsistente ({ruta.gemini_cantidad})"
    return "—"


def confirmar_punto(request, token):
    ruta = get_object_or_404(
        Ruta.objects.select_related("punto"),
        token_confirmacion=token,
    )
    template = "core/confirmar_punto.html"

    if request.method != "POST":
        return render(
            request,
            template,
            {
                "ruta": ruta,
                "formulario_abierto": _puede_confirmar(ruta),
            },
        )

    respuesta = request.POST.get("confirmacion", "").strip()
    if respuesta not in (Ruta.Confirmacion.SI, Ruta.Confirmacion.NO):
        return render(
            request,
            template,
            {
                "ruta": ruta,
                "formulario_abierto": _puede_confirmar(ruta),
                "error": "Elegí Sí o No.",
            },
        )

    filas = (
        Ruta.objects.filter(
            pk=ruta.pk,
            confirmacion__isnull=True,
        )
        .exclude(estado=Ruta.Estado.PAGADO)
        .update(
            confirmacion=respuesta,
            confirmado_en=timezone.now(),
        )
    )
    ruta = Ruta.objects.select_related("punto").get(pk=ruta.pk)

    if filas == 0:
        return render(
            request,
            template,
            {
                "ruta": ruta,
                "formulario_abierto": False,
            },
        )

    intentar_pago_si_corresponde(sender=Ruta, instance=ruta)
    ruta = Ruta.objects.select_related("punto").get(pk=ruta.pk)
    return render(
        request,
        template,
        {
            "ruta": ruta,
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


def _url_confirmacion(request, ruta):
    if not ruta.token_confirmacion:
        return ""
    return request.build_absolute_uri(
        reverse("confirmar_punto", kwargs={"token": ruta.token_confirmacion})
    )


def _url_foto(ruta):
    if not ruta.foto:
        return ""
    return ruta.foto.url


def _puede_proceder_pago(ruta):
    """El local dijo que sí y Gemini no coincidió: el operador puede pagar igual."""
    if ruta.confirmacion != Ruta.Confirmacion.SI:
        return False
    if ruta.gemini_consistente is not False:
        return False
    if ruta.estado in (Ruta.Estado.PAGADO, Ruta.Estado.RECHAZADO):
        return False
    if Payment.objects.filter(ruta=ruta).exists():
        return False
    return True


def _json_ruta_operador(request, ruta):
    return {
        "id": ruta.pk,
        "nombre_local": ruta.punto.nombre,
        "estado": ruta.estado,
        "estado_display": ruta.get_estado_display(),
        "cantidad_baldes": ruta.cantidad_baldes,
        "gemini": _texto_gemini(ruta),
        "confirmacion_display": ruta.get_confirmacion_display() or "—",
        "motivo_no_pago": ruta.motivo_no_pago or "",
        "url_confirmacion": _url_confirmacion(request, ruta),
        "foto_url": _url_foto(ruta),
        "fecha": fecha_hora(ruta.creado_en),
        "recolector": ruta.recolector.nombre,
        "monto": str(ruta.monto),
        "cantidad_promedio": ruta.punto.cantidad_promedio,
        "comision_display": _comision_pagada_display(ruta),
        "puede_proceder_pago": _puede_proceder_pago(ruta),
    }


def _pagos_queryset(**filtro):
    return (
        Payment.objects.filter(**filtro)
        .select_related("ruta", "ruta__punto", "ruta__recolector")
        .order_by("-fecha", "-id")
    )


def _saldo_wallet_display(direccion):
    saldo = consultar_saldo_xlm(direccion)
    if saldo is None:
        return ""
    return f"{number_format(saldo, decimal_pos=7)} XLM"


def _url_cuenta_stellar(direccion):
    direccion = (direccion or "").strip()
    if not direccion:
        return ""
    return STELLAR_EXPERT_ACCOUNT.format(direccion)


def _json_pago(pago, *, para_operador):
    datos = {
        "id": pago.pk,
        "local": pago.ruta.punto.nombre,
        "fecha": fecha_hora(pago.fecha),
        "monto_display": f"{number_format(pago.monto, decimal_pos=7)} XLM",
        "comision_display": f"{number_format(pago.comision, decimal_pos=7)} XLM",
        "tx_url": STELLAR_EXPERT_TX.format(pago.tx_hash) if pago.tx_hash else "",
    }
    if para_operador:
        datos["recolector"] = pago.ruta.recolector.nombre
        datos["ruta_url"] = reverse("detalle_ruta_operador", args=[pago.ruta_id])
    return datos


def _motivo_para_recolector(ruta):
    if ruta.estado != Ruta.Estado.RECHAZADO:
        return ""
    return (ruta.motivo_no_pago or "").strip()


def _json_ruta_recolector(ruta):
    puede_subir = _puede_subir_foto(ruta)
    return {
        "id": ruta.pk,
        "nombre_local": ruta.punto.nombre,
        "inicio": fecha_hora(ruta.creado_en) or "—",
        "fin": fecha_hora(ruta.procesado_en) or "—",
        "estado": ruta.estado,
        "estado_display": ruta.get_estado_display(),
        "motivo_no_pago": _motivo_para_recolector(ruta),
        "detalle_url": reverse("detalle_ruta_recolector", args=[ruta.pk]),
        "tiene_foto": bool(ruta.foto),
        "puede_subir": puede_subir,
        "subir_url": reverse("subir_foto", args=[ruta.pk]) if puede_subir else "",
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
    rutas = (
        Ruta.objects.filter(recolector=recolector)
        .select_related("punto")
        .defer("token_confirmacion")
        .order_by("-creado_en", "-id")
    )
    return render(
        request,
        "core/panel_recolector.html",
        {"recolector": recolector, "rutas": rutas},
    )


@login_required
def subir_foto(request, ruta_id):
    recolector = _recolector_actual(request)
    ruta = get_object_or_404(
        Ruta.objects.select_related("punto").defer("token_confirmacion"),
        pk=ruta_id,
        recolector=recolector,
    )
    if not _puede_subir_foto(ruta):
        messages.error(
            request,
            "Esta ruta ya no admite una foto nueva.",
        )
        return redirect("panel_recolector")

    if request.method != "POST":
        return render(request, "core/subir_foto.html", {"ruta": ruta})

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
        return render(request, "core/subir_foto.html", {"ruta": ruta})

    ruta.foto = foto
    ruta.cantidad_baldes = cantidad
    ruta.save()
    ruta.asegurar_token()

    ruta.foto.open("rb")
    try:
        foto_bytes = ruta.foto.read()
    finally:
        ruta.foto.close()
    mime_type = getattr(foto, "content_type", "") or "image/jpeg"

    resultado = chequear_consistencia(
        foto_bytes=foto_bytes,
        mime_type=mime_type,
        cantidad_reportada=cantidad,
    )
    ruta.gemini_cantidad = resultado.cantidad
    ruta.gemini_consistente = resultado.consistente
    ruta.gemini_respuesta = resultado.respuesta
    ruta.gemini_error = resultado.error
    if ruta.procesado_en is None:
        ruta.procesado_en = timezone.now()
    ruta.save(
        update_fields=[
            "gemini_cantidad",
            "gemini_consistente",
            "gemini_respuesta",
            "gemini_error",
            "procesado_en",
        ]
    )
    messages.success(request, f"Foto recibida para «{ruta.punto.nombre}».")
    return redirect("panel_recolector")


@login_required
def detalle_ruta_recolector(request, ruta_id):
    recolector = _recolector_actual(request)
    ruta = get_object_or_404(
        Ruta.objects.select_related("punto").defer("token_confirmacion"),
        pk=ruta_id,
        recolector=recolector,
    )
    return render(
        request,
        "core/detalle_ruta_recolector.html",
        {
            "recolector": recolector,
            "ruta": ruta,
            "motivo_no_pago": _motivo_para_recolector(ruta),
        },
    )


@login_required
def panel_operador(request):
    operador = _operador_actual(request)
    rutas = (
        Ruta.objects.filter(operador__user=request.user)
        .select_related("recolector", "punto")
        .order_by("-fecha", "-id")
    )
    return render(
        request,
        "core/panel_operador.html",
        {"operador": operador, "rutas": rutas},
    )


@login_required
def puntos_operador(request):
    operador = _operador_actual(request)
    puntos = Punto.objects.filter(operador=operador)
    return render(
        request,
        "core/puntos_operador.html",
        {"operador": operador, "puntos": puntos},
    )


@login_required
def crear_punto_operador(request):
    operador = _operador_actual(request)
    volver_a_ruta = request.POST.get("volver") == "ruta" or request.GET.get("volver") == "ruta"
    form = PuntoOperadorForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        punto = form.save(commit=False)
        punto.operador = operador
        try:
            punto.save()
        except IntegrityError:
            form.add_error("nombre", "Ya tenés un punto de recojo con ese nombre.")
        else:
            messages.success(request, f"Punto «{punto.nombre}» creado.")
            if volver_a_ruta:
                return redirect("crear_ruta_operador")
            return redirect("puntos_operador")
    return render(
        request,
        "core/crear_punto_operador.html",
        {"operador": operador, "form": form, "volver_a_ruta": volver_a_ruta},
    )


@login_required
def crear_ruta_operador(request):
    operador = _operador_actual(request)
    hay_puntos = Punto.objects.filter(operador=operador).exists()
    if not hay_puntos:
        return render(
            request,
            "core/crear_ruta_operador.html",
            {"operador": operador, "hay_puntos": False},
        )
    form = RutaOperadorForm(operador, request.POST or None)
    if request.method == "POST" and form.is_valid():
        ruta = form.save(commit=False)
        ruta.operador = operador
        try:
            ruta.clean()
            ruta.save()
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, f"Ruta de «{ruta.punto.nombre}» creada.")
            return redirect("panel_operador")
    return render(
        request,
        "core/crear_ruta_operador.html",
        {
            "operador": operador,
            "form": form,
            "hay_puntos": True,
            "hay_recolectores": form.fields["recolector"].queryset.exists(),
        },
    )


@login_required
def detalle_ruta_operador(request, ruta_id):
    operador = _operador_actual(request)
    ruta = get_object_or_404(
        Ruta.objects.select_related("recolector", "punto"),
        pk=ruta_id,
        operador__user=request.user,
    )
    return render(
        request,
        "core/detalle_ruta_operador.html",
        {
            "operador": operador,
            "ruta": ruta,
            "url_confirmacion": _url_confirmacion(request, ruta),
            "texto_gemini": _texto_gemini(ruta),
            "comision_display": _comision_pagada_display(ruta),
            "puede_proceder_pago": _puede_proceder_pago(ruta),
        },
    )


@login_required
@require_POST
def proceder_pago_operador(request, ruta_id):
    _operador_actual(request)
    ruta = get_object_or_404(
        Ruta.objects.select_related("recolector", "punto"),
        pk=ruta_id,
        operador__user=request.user,
    )
    if not _puede_proceder_pago(ruta):
        messages.error(request, "Esta ruta no admite proceder con el pago.")
        return redirect("detalle_ruta_operador", ruta_id=ruta.pk)

    decision = request.POST.get("decision", "")
    if decision == "no":
        motivo = (request.POST.get("motivo") or "").strip()
        if not motivo:
            messages.error(request, "Escribí el motivo del no pago.")
            return render(
                request,
                "core/detalle_ruta_operador.html",
                {
                    "operador": request.user.operador,
                    "ruta": ruta,
                    "url_confirmacion": _url_confirmacion(request, ruta),
                    "texto_gemini": _texto_gemini(ruta),
                    "comision_display": _comision_pagada_display(ruta),
                    "puede_proceder_pago": True,
                    "mostrar_rechazo": True,
                    "motivo_rechazo": request.POST.get("motivo") or "",
                },
            )
        Ruta.objects.filter(pk=ruta.pk).update(
            estado=Ruta.Estado.RECHAZADO,
            motivo_no_pago=motivo,
        )
        messages.success(request, f"Pago rechazado para «{ruta.punto.nombre}».")
        return redirect("detalle_ruta_operador", ruta_id=ruta.pk)

    if decision != "si":
        messages.error(request, "Elegí Sí o No.")
        return redirect("detalle_ruta_operador", ruta_id=ruta.pk)

    intentar_pago_si_corresponde(sender=Ruta, instance=ruta, forzar_conteo=True)
    ruta.refresh_from_db()
    if ruta.estado == Ruta.Estado.PAGADO:
        messages.success(request, f"Pago enviado para «{ruta.punto.nombre}».")
    else:
        messages.error(
            request,
            ruta.motivo_no_pago or "No se pudo completar el pago.",
        )
    return redirect("detalle_ruta_operador", ruta_id=ruta.pk)


@login_required
def estado_panel_operador(request):
    _operador_actual(request)
    rutas = (
        Ruta.objects.filter(operador__user=request.user)
        .select_related("recolector", "punto")
        .order_by("-fecha", "-id")
    )
    return JsonResponse(
        {
            "rutas": [
                {
                    "id": ruta.pk,
                    "nombre": ruta.punto.nombre,
                    "fecha": fecha_hora(ruta.creado_en),
                    "recolector": ruta.recolector.nombre,
                    "estado": ruta.estado,
                    "estado_display": ruta.get_estado_display(),
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
        Ruta.objects.select_related("recolector", "punto"),
        pk=ruta_id,
        operador__user=request.user,
    )
    return JsonResponse(_json_ruta_operador(request, ruta))


@login_required
def estado_panel_recolector(request):
    recolector = _recolector_actual(request)
    rutas = (
        Ruta.objects.filter(recolector=recolector)
        .select_related("punto")
        .defer("token_confirmacion")
        .order_by("-creado_en", "-id")
    )
    return JsonResponse(
        {"rutas": [_json_ruta_recolector(ruta) for ruta in rutas]}
    )


def estado_confirmar_punto(request, token):
    ruta = get_object_or_404(Ruta, token_confirmacion=token)
    return JsonResponse(
        {
            "formulario_abierto": _puede_confirmar(ruta),
            "confirmacion_display": ruta.get_confirmacion_display() or "",
        }
    )


@login_required
def pagos_recolector(request):
    recolector = _recolector_actual(request)
    pagos = _pagos_queryset(ruta__recolector=recolector)
    return render(
        request,
        "core/pagos_recolector.html",
        {
            "recolector": recolector,
            "pagos": pagos,
            "saldo_display": _saldo_wallet_display(recolector.direccion_stellar),
            "wallet_url": _url_cuenta_stellar(recolector.direccion_stellar),
        },
    )


@login_required
def estado_pagos_recolector(request):
    recolector = _recolector_actual(request)
    pagos = _pagos_queryset(ruta__recolector=recolector)
    return JsonResponse(
        {
            "saldo_display": _saldo_wallet_display(recolector.direccion_stellar),
            "pagos": [_json_pago(pago, para_operador=False) for pago in pagos],
        }
    )


@login_required
def pagos_operador(request):
    operador = _operador_actual(request)
    pagos = _pagos_queryset(ruta__operador=operador)
    return render(
        request,
        "core/pagos_operador.html",
        {
            "operador": operador,
            "pagos": pagos,
            "saldo_display": _saldo_wallet_display(direccion_cuenta_pagadora()),
            "wallet_url": _url_cuenta_stellar(operador.direccion_stellar),
        },
    )


@login_required
def estado_pagos_operador(request):
    _operador_actual(request)
    pagos = _pagos_queryset(ruta__operador__user=request.user)
    return JsonResponse(
        {
            "saldo_display": _saldo_wallet_display(direccion_cuenta_pagadora()),
            "pagos": [_json_pago(pago, para_operador=True) for pago in pagos],
        }
    )
