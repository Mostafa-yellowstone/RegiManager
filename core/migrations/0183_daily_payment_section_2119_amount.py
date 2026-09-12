from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0182_daily_payment_section_2119_cc_fee"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="dailypaymenttransaction",
            name="section_2119",
        ),
        migrations.AddField(
            model_name="dailypaymenttransaction",
            name="section_2119",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Section 2119 fee amount shown on new business / renewal receipts.",
                max_digits=12,
                null=True,
            ),
        ),
    ]
