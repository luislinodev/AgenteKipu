import secrets
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import IntegrityError, models

XLM = Decimal("0.0000001")


def _validar_clave_publica(valor):
    valor = (valor or "").strip()
    if valor.startswith("S"):
        raise ValidationError(
            "Pegá la clave pública, que empieza con G. La que empieza con S es secreta."
        )
    try:
        from stellar_sdk import Keypair

        Keypair.from_public_key(valor)
    except Exception:
        raise ValidationError(
            "Tiene que ser una clave pública de Stellar (56 caracteres, empieza con G)."
        ) from None
    return valor


class Operador(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="operador",
    )
    direccion_stellar = models.CharField(
        max_length=56,
        verbose_name="clave pública",
        help_text="Clave pública de la wallet en Stellar. Empieza con G. No pegues la clave secreta.",
    )

    class Meta:
        ordering = ["user__username"]

    def __str__(self):
        if not self.user_id:
            return "Operador"
        return (self.user.get_full_name() or "").strip() or self.user.username

    def clean(self):
        super().clean()
        self.direccion_stellar = _validar_clave_publica(self.direccion_stellar)


class Recolector(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="recolector",
    )
    nombre = models.CharField(max_length=120)
    direccion_stellar = models.CharField(max_length=56)

    class Meta:
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre

    def save(self, *args, **kwargs):
        if self.user_id:
            self.nombre = (self.user.get_full_name() or "").strip() or self.user.username
        super().save(*args, **kwargs)


class Punto(models.Model):
    """Catálogo de destinos. Un local se reusa en varias rutas."""

    operador = models.ForeignKey(
        Operador,
        on_delete=models.PROTECT,
        related_name="puntos",
    )
    nombre = models.CharField(max_length=200)
    cantidad_promedio = models.PositiveIntegerField(
        default=0,
        verbose_name="cantidad promedio",
        help_text="Baldes que este local suele entregar. La comisión se calcula sobre lo que supere este número.",
    )
    comision_por_balde = models.DecimalField(
        max_digits=12,
        decimal_places=7,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
        verbose_name="comisión por balde",
        help_text="XLM por cada balde confirmado por encima del promedio. 0 no suma comisión.",
    )

    class Meta:
        ordering = ["nombre"]
        verbose_name = "punto"
        verbose_name_plural = "puntos (catálogo)"
        constraints = [
            models.UniqueConstraint(
                fields=["operador", "nombre"],
                name="punto_unico_por_operador",
            ),
        ]

    def __str__(self):
        return self.nombre


class Ruta(models.Model):
    class Estado(models.TextChoices):
        PENDIENTE = "pendiente", "Pendiente"
        CONFIRMADO = "confirmado", "Confirmado"
        EN_REVISION = "en_revision", "En revisión"
        RECHAZADO = "rechazado", "Rechazado"
        PAGADO = "pagado", "Pagado"

    class Confirmacion(models.TextChoices):
        SI = "si", "Sí"
        NO = "no", "No"

    operador = models.ForeignKey(
        Operador,
        on_delete=models.PROTECT,
        related_name="rutas",
    )
    recolector = models.ForeignKey(
        Recolector,
        on_delete=models.PROTECT,
        related_name="rutas",
    )
    punto = models.ForeignKey(
        Punto,
        on_delete=models.PROTECT,
        related_name="rutas",
    )
    nombre = models.CharField(max_length=200)
    fecha = models.DateField()
    creado_en = models.DateTimeField(auto_now_add=True)
    procesado_en = models.DateTimeField(null=True, blank=True)
    monto = models.DecimalField(max_digits=12, decimal_places=7)

    cantidad_baldes = models.PositiveIntegerField(null=True, blank=True)
    foto = models.ImageField(upload_to="puntos/", blank=True)

    gemini_cantidad = models.PositiveIntegerField(null=True, blank=True)
    gemini_consistente = models.BooleanField(null=True, blank=True)
    gemini_respuesta = models.TextField(blank=True)
    gemini_error = models.TextField(blank=True)

    token_confirmacion = models.CharField(
        max_length=64,
        unique=True,
        null=True,
        blank=True,
    )
    confirmacion = models.CharField(
        max_length=2,
        choices=Confirmacion.choices,
        null=True,
        blank=True,
    )
    confirmado_en = models.DateTimeField(null=True, blank=True)

    estado = models.CharField(
        max_length=20,
        choices=Estado.choices,
        default=Estado.PENDIENTE,
    )
    motivo_no_pago = models.TextField(blank=True)

    class Meta:
        ordering = ["-fecha", "-id"]

    def __str__(self):
        return f"{self.punto} · {self.fecha}"

    def clean(self):
        if self.punto_id:
            if self.operador_id and self.punto.operador_id != self.operador_id:
                raise ValidationError(
                    "El local tiene que ser del mismo operador que la ruta."
                )
            if not self.operador_id:
                self.operador = self.punto.operador

    def save(self, *args, **kwargs):
        if self.punto_id:
            self.nombre = self.punto.nombre
            if not self.operador_id:
                self.operador_id = self.punto.operador_id
        super().save(*args, **kwargs)

    def comision_confirmada(self) -> Decimal:
        """XLM extra por baldes confirmados por encima del promedio del local."""
        baldes = self.cantidad_baldes or 0
        excedente = baldes - self.punto.cantidad_promedio
        if excedente <= 0:
            return Decimal("0")
        return (Decimal(excedente) * self.punto.comision_por_balde).quantize(XLM)

    def monto_a_pagar(self) -> Decimal:
        return (self.monto + self.comision_confirmada()).quantize(XLM)

    def asegurar_token(self) -> str:
        if self.token_confirmacion:
            return self.token_confirmacion
        if not self.pk:
            raise ValueError("Hay que guardar la Ruta antes de generar el token.")
        for _ in range(8):
            self.token_confirmacion = secrets.token_urlsafe(32)
            try:
                self.save(update_fields=["token_confirmacion"])
                return self.token_confirmacion
            except IntegrityError:
                self.token_confirmacion = None
        raise RuntimeError("No se pudo generar un token de confirmación único.")


class Payment(models.Model):
    class Estado(models.TextChoices):
        PENDIENTE = "pendiente", "Pendiente"
        ENVIADA = "enviada", "Enviada"
        CONFIRMADA = "confirmada", "Confirmada"
        COMPLETADO = "completado", "Completado"
        FALLIDA = "fallida", "Fallida"

    ruta = models.OneToOneField(
        Ruta,
        on_delete=models.CASCADE,
        related_name="payment",
    )
    tx_hash = models.CharField(max_length=64, blank=True)
    monto = models.DecimalField(max_digits=12, decimal_places=7)
    comision = models.DecimalField(
        max_digits=12,
        decimal_places=7,
        default=Decimal("0"),
        verbose_name="comisión",
        help_text="Parte del monto que corresponde a baldes por encima del promedio, calculada al pagar.",
    )
    fecha = models.DateTimeField(auto_now_add=True)
    estado = models.CharField(
        max_length=20,
        choices=Estado.choices,
        default=Estado.PENDIENTE,
    )

    class Meta:
        ordering = ["-fecha"]

    def __str__(self):
        return f"Pago de {self.ruta}"
