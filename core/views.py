import logging
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from .models import Task, Worker

logger = logging.getLogger(__name__)


def dashboard(request):
    tasks = Task.objects.select_related("worker")
    return render(request, "core/dashboard.html", {"tasks": tasks})


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


def marcar_verificada(request, task_id):
    if request.method != "POST":
        return redirect("dashboard")

    task = get_object_or_404(Task.objects.select_related("worker"), pk=task_id)
    if task.estado != Task.Estado.COMPLETADA:
        messages.error(request, "Solo se pueden verificar tareas completadas.")
        return redirect("dashboard")

    try:
        task.estado = Task.Estado.VERIFICADA
        task.save(update_fields=["estado"])
    except Exception:
        logger.exception("Falló al marcar la tarea %s como verificada.", task.pk)
        messages.error(
            request,
            "No se pudo verificar la tarea. El request no se interrumpió; revisa el log.",
        )
        return redirect("dashboard")

    if getattr(task, "pago_ok", None):
        messages.success(
            request,
            f"Tarea «{task.titulo}» pagada. Hash: {task.pago_ok}",
        )
    elif getattr(task, "pago_error", None):
        messages.error(
            request,
            f"Tarea «{task.titulo}» quedó verificada, pero el pago no se envió: "
            f"{task.pago_error}",
        )
    else:
        messages.success(request, f"Tarea «{task.titulo}» marcada como verificada.")
    return redirect("dashboard")


def detalle_pago(request, task_id):
    task = get_object_or_404(Task.objects.select_related("worker"), pk=task_id)
    payment = getattr(task, "payment", None)
    return render(
        request,
        "core/detalle_pago.html",
        {"task": task, "payment": payment},
    )
