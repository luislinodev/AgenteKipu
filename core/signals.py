import logging

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .models import Payment, Task
from .stellar_agent import (
    FondosInsuficientesError,
    HorizonTransactionError,
    procesar_pago,
)

logger = logging.getLogger(__name__)


@receiver(pre_save, sender=Task)
def recordar_estado_anterior(sender, instance, **kwargs):
    if not instance.pk:
        instance._estado_anterior = None
        return
    estado_en_db = (
        Task.objects.filter(pk=instance.pk).values_list("estado", flat=True).first()
    )
    instance._estado_anterior = estado_en_db


@receiver(post_save, sender=Task)
def pagar_al_verificar(sender, instance, created, **kwargs):
    estado_anterior = getattr(instance, "_estado_anterior", None)
    acaba_de_verificarse = instance.estado == "verificada" and (
        created or estado_anterior != "verificada"
    )
    if not acaba_de_verificarse:
        return

    if Payment.objects.filter(task=instance).exists():
        logger.warning(
            "La tarea %s ya tiene un Payment. No se vuelve a llamar a procesar_pago.",
            instance.pk,
        )
        return

    try:
        tx_hash = procesar_pago(instance)
        Payment.objects.create(
            task=instance,
            tx_hash=tx_hash,
            monto=instance.monto,
            estado="completado",
        )
        Task.objects.filter(pk=instance.pk).update(estado="pagada")
        instance.estado = "pagada"
        instance.pago_ok = tx_hash
        logger.info(
            "Pago enviado para tarea %s. hash=%s monto=%s",
            instance.pk,
            tx_hash,
            instance.monto,
        )
    except (FondosInsuficientesError, HorizonTransactionError) as exc:
        instance.pago_error = str(exc)
        logger.error(
            "Pago no enviado. Tarea %s permanece verificada. %s",
            instance.pk,
            exc,
        )
    except Exception as exc:
        instance.pago_error = (
            "No se pudo completar el pago automático. Revisa el log de la consola."
        )
        logger.exception(
            "Error no controlado al pagar la tarea %s: %s",
            instance.pk,
            exc,
        )
