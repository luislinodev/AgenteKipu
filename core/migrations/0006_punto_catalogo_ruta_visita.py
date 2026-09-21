from collections import defaultdict
from decimal import Decimal

from django.db import migrations, models
import django.db.models.deletion


def copiar_visitas_a_rutas(apps, schema_editor):
    Ruta = apps.get_model("core", "Ruta")
    Visita = apps.get_model("core", "Punto")
    Catalogo = apps.get_model("core", "PuntoCatalogo")
    Payment = apps.get_model("core", "Payment")

    catalogo = {}
    por_ruta = defaultdict(list)
    for visita in Visita.objects.all().order_by("id"):
        por_ruta[visita.ruta_id].append(visita)

    campos_visita = (
        "monto",
        "cantidad_baldes",
        "foto",
        "gemini_cantidad",
        "gemini_consistente",
        "gemini_respuesta",
        "gemini_error",
        "token_confirmacion",
        "confirmacion",
        "confirmado_en",
        "estado",
        "motivo_no_pago",
    )

    def catalogo_id(operador_id, nombre):
        nombre = (nombre or "").strip() or "Sin nombre"
        clave = (operador_id, nombre)
        if clave not in catalogo:
            item = Catalogo.objects.create(operador_id=operador_id, nombre=nombre)
            catalogo[clave] = item.pk
        return catalogo[clave]

    def aplicar(destino, visita, cat_id):
        destino.punto_catalogo_id = cat_id
        destino.nombre = (visita.nombre_local or "").strip() or destino.nombre
        for campo in campos_visita:
            setattr(destino, campo, getattr(visita, campo))
        destino.save()
        Payment.objects.filter(punto_id=visita.pk).update(ruta_id=destino.pk)

    for ruta_id, visitas in por_ruta.items():
        ruta = Ruta.objects.get(pk=ruta_id)
        for indice, visita in enumerate(visitas):
            cat_id = catalogo_id(ruta.operador_id, visita.nombre_local)
            if indice == 0:
                aplicar(ruta, visita, cat_id)
                continue
            nueva = Ruta.objects.create(
                operador_id=ruta.operador_id,
                recolector_id=ruta.recolector_id,
                nombre=ruta.nombre,
                fecha=ruta.fecha,
                monto=visita.monto or Decimal("0"),
            )
            aplicar(nueva, visita, cat_id)

    Ruta.objects.filter(punto_catalogo_id__isnull=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0005_quitar_worker_task"),
    ]

    operations = [
        migrations.CreateModel(
            name="PuntoCatalogo",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("nombre", models.CharField(max_length=200)),
                (
                    "operador",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="puntos",
                        to="core.operador",
                    ),
                ),
            ],
            options={"ordering": ["nombre"]},
        ),
        migrations.AddField(
            model_name="ruta",
            name="punto_catalogo",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="rutas",
                to="core.puntocatalogo",
            ),
        ),
        migrations.AddField(
            model_name="ruta",
            name="monto",
            field=models.DecimalField(
                decimal_places=7, default=Decimal("0"), max_digits=12
            ),
        ),
        migrations.AddField(
            model_name="ruta",
            name="cantidad_baldes",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="ruta",
            name="foto",
            field=models.ImageField(blank=True, upload_to="puntos/"),
        ),
        migrations.AddField(
            model_name="ruta",
            name="gemini_cantidad",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="ruta",
            name="gemini_consistente",
            field=models.BooleanField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="ruta",
            name="gemini_respuesta",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="ruta",
            name="gemini_error",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="ruta",
            name="token_confirmacion",
            field=models.CharField(blank=True, max_length=64, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="ruta",
            name="confirmacion",
            field=models.CharField(
                blank=True,
                choices=[("si", "Sí"), ("no", "No")],
                max_length=2,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="ruta",
            name="confirmado_en",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="ruta",
            name="estado",
            field=models.CharField(
                choices=[
                    ("pendiente", "Pendiente"),
                    ("confirmado", "Confirmado"),
                    ("en_revision", "En revisión"),
                    ("pagado", "Pagado"),
                ],
                default="pendiente",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="ruta",
            name="motivo_no_pago",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="payment",
            name="ruta",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="payment_tmp",
                to="core.ruta",
            ),
        ),
        migrations.RunPython(copiar_visitas_a_rutas, migrations.RunPython.noop),
        migrations.RemoveField(model_name="payment", name="punto"),
        migrations.AlterField(
            model_name="payment",
            name="ruta",
            field=models.OneToOneField(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="payment",
                to="core.ruta",
            ),
        ),
        migrations.DeleteModel(name="Punto"),
        migrations.RenameModel(old_name="PuntoCatalogo", new_name="Punto"),
        migrations.RenameField(
            model_name="ruta",
            old_name="punto_catalogo",
            new_name="punto",
        ),
        migrations.AlterField(
            model_name="ruta",
            name="punto",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="rutas",
                to="core.punto",
            ),
        ),
        migrations.AddConstraint(
            model_name="punto",
            constraint=models.UniqueConstraint(
                fields=("operador", "nombre"),
                name="punto_unico_por_operador",
            ),
        ),
    ]
