import logging

from django.db import IntegrityError
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Payment, Punto
from .stellar_agent import (
    FondosInsuficientesError,
    HorizonTransactionError,
    procesar_pago,
)

logger = logging.getLogger(__name__)


class _OrdenPago:
    """Datos mínimos para stellar_agent, sin acoplarlo a Django."""

    def __init__(self, punto):
        self.pk = punto.pk
        self.monto = punto.monto
        self.direccion_stellar = punto.ruta.recolector.direccion_stellar


def _marcar_en_revision(punto, motivo):
    if punto.estado == Punto.Estado.PAGADO:
        return
    if punto.estado == Punto.Estado.EN_REVISION and punto.motivo_no_pago == motivo:
        return
    Punto.objects.filter(pk=punto.pk).update(
        estado=Punto.Estado.EN_REVISION,
        motivo_no_pago=motivo,
    )
    punto.estado = Punto.Estado.EN_REVISION
    punto.motivo_no_pago = motivo


@receiver(post_save, sender=Punto)
def intentar_pago_si_corresponde(sender, instance, **kwargs):
    if instance.estado == Punto.Estado.PAGADO:
        return

    if Payment.objects.filter(punto=instance).exists():
        logger.warning(
            "El punto %s ya tiene un Payment. No se vuelve a llamar a procesar_pago.",
            instance.pk,
        )
        return

    # Sin la señal del local, Gemini no cambia el estado ni cierra la confirmación.
    if instance.confirmacion is None:
        return

    if instance.confirmacion == Punto.Confirmacion.NO:
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
        if instance.estado == Punto.Estado.PENDIENTE:
            Punto.objects.filter(pk=instance.pk).update(
                estado=Punto.Estado.CONFIRMADO
            )
            instance.estado = Punto.Estado.CONFIRMADO
        return

    try:
        payment = Payment.objects.create(
            punto=instance,
            tx_hash="",
            monto=instance.monto,
            estado="pendiente",
        )
    except IntegrityError:
        logger.warning(
            "El punto %s ya tiene un Payment (carrera en el INSERT). "
            "No se llama a procesar_pago.",
            instance.pk,
        )
        return

    try:
        tx_hash = procesar_pago(_OrdenPago(instance))
        payment.tx_hash = tx_hash
        payment.estado = "completado"
        payment.save(update_fields=["tx_hash", "estado"])
        Punto.objects.filter(pk=instance.pk).update(estado=Punto.Estado.PAGADO)
        instance.estado = Punto.Estado.PAGADO
        instance.pago_ok = tx_hash
        logger.info(
            "Pago enviado para punto %s. hash=%s monto=%s",
            instance.pk,
            tx_hash,
            instance.monto,
        )
    except (FondosInsuficientesError, HorizonTransactionError) as exc:
        payment.delete()
        _marcar_en_revision(instance, str(exc))
        logger.error(
            "Pago no enviado. Punto %s no queda pagado. %s",
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
            "Error no controlado al pagar el punto %s: %s",
            instance.pk,
            exc,
        )
