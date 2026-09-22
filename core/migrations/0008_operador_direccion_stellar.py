from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0007_punto_verbose_name"),
    ]

    operations = [
        migrations.AddField(
            model_name="operador",
            name="direccion_stellar",
            field=models.CharField(
                default="",
                help_text="Clave pública de la wallet en Stellar. Empieza con G. No pegues la clave secreta.",
                max_length=56,
                verbose_name="clave pública",
            ),
            preserve_default=False,
        ),
    ]
