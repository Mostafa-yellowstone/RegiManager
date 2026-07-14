from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0146_tlc_payment_receipts"),
    ]

    operations = [
        migrations.AddField(
            model_name="space",
            name="logo",
            field=models.ImageField(
                blank=True,
                help_text="Custom logo shown on the Spaces home cards and space documents/receipts.",
                null=True,
                upload_to="space_logos/",
            ),
        ),
        migrations.AlterField(
            model_name="space",
            name="business_address",
            field=models.TextField(
                blank=True,
                default="",
                help_text="Address shown on space invoices, reports, and receipts",
            ),
        ),
    ]
