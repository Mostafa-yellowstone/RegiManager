from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0094_inventory_crm"),
    ]

    operations = [
        migrations.AddField(
            model_name="space",
            name="business_address",
            field=models.TextField(
                blank=True,
                default="",
                help_text="Address shown on custom inventory invoices and reports",
            ),
        ),
        migrations.AddField(
            model_name="space",
            name="business_email",
            field=models.EmailField(blank=True, default="", max_length=254),
        ),
        migrations.AddField(
            model_name="space",
            name="business_phone",
            field=models.CharField(blank=True, default="", max_length=40),
        ),
        migrations.AddField(
            model_name="inventoryinvoice",
            name="buyer_address",
            field=models.TextField(blank=True, default=""),
        ),
    ]
