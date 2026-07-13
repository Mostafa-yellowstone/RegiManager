from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0143_tlc_carrier_registry"),
    ]

    operations = [
        migrations.AddField(
            model_name="tlcpolicycancellation",
            name="earned_commission_at_cancel",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0.00"),
                help_text="Installment commission already earned when the policy was cancelled.",
                max_digits=12,
            ),
        ),
        migrations.AddField(
            model_name="tlcpolicycancellation",
            name="return_premium",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0.00"),
                help_text="Prorated unearned premium owed back after cancellation.",
                max_digits=12,
            ),
        ),
        migrations.AddField(
            model_name="tlcpolicycancellation",
            name="unearned_commission",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0.00"),
                help_text="Prorated commission to return to the carrier after cancellation.",
                max_digits=12,
            ),
        ),
    ]
