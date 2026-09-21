import secrets

from django.conf import settings
from django.db import IntegrityError, models


class Worker(models.Model):
    nombre = models.CharField(max_length=120)
    direccion_stellar = models.CharField(max_length=56)

    class Meta:
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class Task(models.Model):
    class Estado(models.TextChoices):
        PENDIENTE = "pendiente", "Pendiente"
        COMPLETADA = "completada", "Completada"
        VERIFICADA = "verificada", "Verificada"
        PAGADA = "pagada", "Pagada"

    titulo = models.CharField(max_length=200)
    descripcion = models.TextField(blank=True)
    monto = models.DecimalField(max_digits=12, decimal_places=7)
    worker = models.ForeignKey(
        Worker,
        on_delete=models.PROTECT,
        related_name="tasks",
    )
    estado = models.CharField(
        max_length=20,
        choices=Estado.choices,
        default=Estado.PENDIENTE,
    )

    class Meta:
        ordering = ["-id"]

    def __str__(self):
        return self.titulo


class Operador(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="operador",
    )
    nombre = models.CharField(max_length=120)

    class Meta:
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


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


class Ruta(models.Model):
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
    nombre = models.CharField(max_length=200)
    fecha = models.DateField()

    class Meta:
        ordering = ["-fecha", "-id"]

    def __str__(self):
        return self.nombre


class Punto(models.Model):
    class Estado(models.TextChoices):
        PENDIENTE = "pendiente", "Pendiente"
        CONFIRMADO = "confirmado", "Confirmado"
        EN_REVISION = "en_revision", "En revisión"
        PAGADO = "pagado", "Pagado"

    class Confirmacion(models.TextChoices):
        SI = "si", "Sí"
        NO = "no", "No"

    ruta = models.ForeignKey(
        Ruta,
        on_delete=models.CASCADE,
        related_name="puntos",
    )
    nombre_local = models.CharField(max_length=200)
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
        ordering = ["id"]

    def __str__(self):
        return f"{self.nombre_local} ({self.ruta})"

    def asegurar_token(self) -> str:
        if self.token_confirmacion:
            return self.token_confirmacion
        if not self.pk:
            raise ValueError("Hay que guardar el Punto antes de generar el token.")
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

    punto = models.OneToOneField(
        Punto,
        on_delete=models.CASCADE,
        related_name="payment",
    )
    tx_hash = models.CharField(max_length=64, blank=True)
    monto = models.DecimalField(max_digits=12, decimal_places=7)
    fecha = models.DateTimeField(auto_now_add=True)
    estado = models.CharField(
        max_length=20,
        choices=Estado.choices,
        default=Estado.PENDIENTE,
    )

    class Meta:
        ordering = ["-fecha"]

    def __str__(self):
        return f"Pago de {self.punto}"
