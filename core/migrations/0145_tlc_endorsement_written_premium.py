from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0144_tlc_cancellation_accounting"),
    ]

    operations = [
        migrations.AddField(
            model_name="tlcendorsement",
            name="endorsement_fee",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0.00"),
                help_text="Carrier endorsement fee charged on this change.",
                max_digits=12,
            ),
        ),
        migrations.AddField(
            model_name="tlcendorsement",
            name="written_premium_after",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0.00"),
                help_text="New total written premium after this endorsement (including endorsement fees).",
                max_digits=12,
            ),
        ),
        migrations.AddField(
            model_name="tlcendorsement",
            name="written_premium_before",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0.00"),
                help_text="Current written premium immediately before this endorsement.",
                max_digits=12,
            ),
        ),
    ]
