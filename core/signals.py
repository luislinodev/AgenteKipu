import logging

from django.db import IntegrityError
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Payment, Ruta
from .stellar_agent import (
    FondosInsuficientesError,
    HorizonTransactionError,
    procesar_pago,
)

logger = logging.getLogger(__name__)


class _OrdenPago:
    """Datos mínimos para stellar_agent, sin acoplarlo a Django."""

    def __init__(self, ruta):
        self.pk = ruta.pk
        self.monto = ruta.monto
        self.direccion_stellar = ruta.recolector.direccion_stellar


def _marcar_en_revision(ruta, motivo):
    if ruta.estado == Ruta.Estado.PAGADO:
        return
    if ruta.estado == Ruta.Estado.EN_REVISION and ruta.motivo_no_pago == motivo:
        return
    Ruta.objects.filter(pk=ruta.pk).update(
        estado=Ruta.Estado.EN_REVISION,
        motivo_no_pago=motivo,
    )
    ruta.estado = Ruta.Estado.EN_REVISION
    ruta.motivo_no_pago = motivo


@receiver(post_save, sender=Ruta)
def intentar_pago_si_corresponde(sender, instance, **kwargs):
    if instance.estado == Ruta.Estado.PAGADO:
        return

    if Payment.objects.filter(ruta=instance).exists():
        logger.warning(
            "La ruta %s ya tiene un Payment. No se vuelve a llamar a procesar_pago.",
            instance.pk,
        )
        return

    if instance.confirmacion is None:
        return

    if instance.confirmacion == Ruta.Confirmacion.NO:
        _marcar_en_revision(instance, "El punto confirmó No.")
        return

    if instance.gemini_error:
        _marcar_en_revision(
            instance,
            "Gemini falló; el punto no se paga solo.",
        )
        return

    if instance.gemini_consistente is False:
        _marcar_en_revision(
            instance,
            "El conteo de Gemini no es consistente con lo reportado.",
        )
        return

    if instance.gemini_consistente is not True:
        if instance.estado == Ruta.Estado.PENDIENTE:
            Ruta.objects.filter(pk=instance.pk).update(
                estado=Ruta.Estado.CONFIRMADO
            )
            instance.estado = Ruta.Estado.CONFIRMADO
        return

    try:
        payment = Payment.objects.create(
            ruta=instance,
            tx_hash="",
            monto=instance.monto,
            estado="pendiente",
        )
    except IntegrityError:
        logger.warning(
            "La ruta %s ya tiene un Payment (carrera en el INSERT). "
            "No se llama a procesar_pago.",
            instance.pk,
        )
        return

    try:
        tx_hash = procesar_pago(_OrdenPago(instance))
        payment.tx_hash = tx_hash
        payment.estado = "completado"
        payment.save(update_fields=["tx_hash", "estado"])
        Ruta.objects.filter(pk=instance.pk).update(estado=Ruta.Estado.PAGADO)
        instance.estado = Ruta.Estado.PAGADO
        instance.pago_ok = tx_hash
        logger.info(
            "Pago enviado para ruta %s. hash=%s monto=%s",
            instance.pk,
            tx_hash,
            instance.monto,
        )
    except (FondosInsuficientesError, HorizonTransactionError) as exc:
        payment.delete()
        _marcar_en_revision(instance, str(exc))
        logger.error(
            "Pago no enviado. Ruta %s no queda pagada. %s",
            instance.pk,
            exc,
        )
    except Exception as exc:
        payment.delete()
        _marcar_en_revision(
            instance,
            "No se pudo completar el pago automático. Revisa el log de la consola.",
        )
        logger.exception(
            "Error no controlado al pagar la ruta %s: %s",
            instance.pk,
            exc,
        )
