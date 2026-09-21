from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0004_payment_apunta_a_punto"),
    ]

    operations = [
        migrations.DeleteModel(
            name="Task",
        ),
        migrations.DeleteModel(
            name="Worker",
        ),
    ]
