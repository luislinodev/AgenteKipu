import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0008_operador_direccion_stellar"),
    ]

    operations = [
        migrations.AddField(
            model_name="ruta",
            name="creado_en",
            field=models.DateTimeField(
                auto_now_add=True,
                default=django.utils.timezone.now,
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="ruta",
            name="procesado_en",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
