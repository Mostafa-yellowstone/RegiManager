from decimal import Decimal
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0096_inventory_suppliers"),
    ]

    operations = [
        migrations.AddField(
            model_name="inventoryinvoice",
            name="sales_tax",
            field=models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12),
        ),
    ]
