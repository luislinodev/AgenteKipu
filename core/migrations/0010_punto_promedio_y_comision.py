from decimal import Decimal

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0009_ruta_creado_en_procesado_en"),
    ]

    operations = [
        migrations.AddField(
            model_name="punto",
            name="cantidad_promedio",
            field=models.PositiveIntegerField(
                default=0,
                help_text="Baldes que este local suele entregar. La comisión se calcula sobre lo que supere este número.",
                verbose_name="cantidad promedio",
            ),
        ),
        migrations.AddField(
            model_name="punto",
            name="comision_por_balde",
            field=models.DecimalField(
                decimal_places=7,
                default=Decimal("0"),
                help_text="XLM por cada balde confirmado por encima del promedio. 0 no suma comisión.",
                max_digits=12,
                validators=[
                    django.core.validators.MinValueValidator(Decimal("0")),
                ],
                verbose_name="comisión por balde",
            ),
        ),
        migrations.AddField(
            model_name="payment",
            name="comision",
            field=models.DecimalField(
                decimal_places=7,
                default=Decimal("0"),
                help_text="Parte del monto que corresponde a baldes por encima del promedio, calculada al pagar.",
                max_digits=12,
                verbose_name="comisión",
            ),
        ),
    ]
