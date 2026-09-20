from django.db import models


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


class Payment(models.Model):
    class Estado(models.TextChoices):
        PENDIENTE = "pendiente", "Pendiente"
        ENVIADA = "enviada", "Enviada"
        CONFIRMADA = "confirmada", "Confirmada"
        COMPLETADO = "completado", "Completado"
        FALLIDA = "fallida", "Fallida"

    task = models.OneToOneField(
        Task,
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
        return f"Pago de {self.task}"
