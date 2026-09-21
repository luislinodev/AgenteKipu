from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from .gemini_check import chequear_consistencia
from .models import Operador, Punto, Recolector, Ruta, Task, Worker
from .signals import intentar_pago_si_corresponde

_ESTADOS_ABIERTOS = (Punto.Estado.PENDIENTE, Punto.Estado.CONFIRMADO)


def dashboard(request):
    if request.user.is_authenticated:
        return redirect("despues_de_entrar")
    return render(request, "core/dashboard.html")


def crear_tarea(request):
    workers = Worker.objects.all()
    if request.method != "POST":
        return render(request, "core/crear_tarea.html", {"workers": workers})

    titulo = request.POST.get("titulo", "").strip()
    descripcion = request.POST.get("descripcion", "").strip()
    monto_raw = request.POST.get("monto", "").strip()
    worker_id = request.POST.get("worker_id", "").strip()
    worker_nombre = request.POST.get("worker_nombre", "").strip()
    worker_direccion = request.POST.get("worker_direccion", "").strip()

    errores = []
    if not titulo:
        errores.append("El título es obligatorio.")

    try:
        monto = Decimal(monto_raw)
        if monto <= 0:
            errores.append("El monto debe ser mayor que cero.")
    except (InvalidOperation, TypeError):
        monto = None
        errores.append("El monto no es válido.")

    worker = None
    if worker_id:
        worker = Worker.objects.filter(pk=worker_id).first()
        if worker is None:
            errores.append("El trabajador seleccionado no existe.")
    elif worker_nombre and worker_direccion:
        worker, _ = Worker.objects.get_or_create(
            direccion_stellar=worker_direccion,
            defaults={"nombre": worker_nombre},
        )
    else:
        errores.append("Elige un trabajador o crea uno nuevo.")

    if errores:
        for error in errores:
            messages.error(request, error)
        return render(request, "core/crear_tarea.html", {"workers": workers})

    Task.objects.create(
        titulo=titulo,
        descripcion=descripcion,
        monto=monto,
        worker=worker,
    )
    messages.success(request, "Tarea creada.")
    return redirect("dashboard")


def marcar_completada(request, task_id):
    if request.method != "POST":
        return redirect("dashboard")

    task = get_object_or_404(Task, pk=task_id)
    if task.estado == Task.Estado.PENDIENTE:
        task.estado = Task.Estado.COMPLETADA
        task.save(update_fields=["estado"])
        messages.success(request, f"Tarea «{task.titulo}» marcada como completada.")
    else:
        messages.error(request, "Solo se pueden completar tareas pendientes.")
    return redirect("dashboard")


def detalle_pago(request, task_id):
    task = get_object_or_404(Task.objects.select_related("worker"), pk=task_id)
    payment = getattr(task, "payment", None)
    return render(
        request,
        "core/detalle_pago.html",
        {"task": task, "payment": payment},
    )


def _puede_confirmar(punto):
    return punto.confirmacion is None and punto.estado in _ESTADOS_ABIERTOS


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

    filas = Punto.objects.filter(
        pk=punto.pk,
        confirmacion__isnull=True,
        estado__in=_ESTADOS_ABIERTOS,
    ).update(
        confirmacion=respuesta,
        confirmado_en=timezone.now(),
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
    if punto.estado == Punto.Estado.PAGADO or punto.confirmacion:
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
        Ruta.objects.select_related("recolector"),
        pk=ruta_id,
        operador__user=request.user,
    )
    filas = [
        {
            "punto": punto,
            "url_confirmacion": _url_confirmacion(request, punto),
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
        },
    )
