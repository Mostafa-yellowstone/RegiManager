from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0130_service_refund_permission"),
    ]

    operations = [
        migrations.AddField(
            model_name="dailypaymenttransaction",
            name="updated_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="dailypaymenttransaction",
            name="updated_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="updated_daily_payments",
                to="auth.user",
            ),
        ),
    ]
