import django.db.models.deletion
from decimal import Decimal
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0095_inventory_business_fields"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="inventoryproduct",
            name="cost_price",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0.00"),
                help_text="Last unit cost from supplier",
                max_digits=12,
            ),
        ),
        migrations.CreateModel(
            name="InventorySupplier",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=200)),
                ("company_name", models.CharField(blank=True, default="", max_length=200)),
                ("contact_person", models.CharField(blank=True, default="", max_length=120)),
                ("phone", models.CharField(blank=True, default="", max_length=40)),
                ("email", models.EmailField(blank=True, default="", max_length=254)),
                ("address", models.TextField(blank=True, default="")),
                ("notes", models.TextField(blank=True, default="")),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="inventory_suppliers",
                        to="core.organization",
                    ),
                ),
                (
                    "space",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="inventory_suppliers",
                        to="core.space",
                    ),
                ),
            ],
            options={
                "ordering": ["name"],
            },
        ),
        migrations.AddField(
            model_name="inventoryproduct",
            name="primary_supplier",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="products",
                to="core.inventorysupplier",
            ),
        ),
        migrations.CreateModel(
            name="InventoryPurchase",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("purchase_number", models.CharField(max_length=40, unique=True)),
                ("purchase_date", models.DateField()),
                ("notes", models.TextField(blank=True, default="")),
                ("total_cost", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="inventory_purchases_created",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="inventory_purchases",
                        to="core.organization",
                    ),
                ),
                (
                    "space",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="inventory_purchases",
                        to="core.space",
                    ),
                ),
                (
                    "supplier",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="purchases",
                        to="core.inventorysupplier",
                    ),
                ),
            ],
            options={
                "ordering": ["-purchase_date", "-created_at"],
            },
        ),
        migrations.CreateModel(
            name="InventoryPurchaseLine",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("description", models.CharField(max_length=255)),
                ("quantity", models.PositiveIntegerField(default=1)),
                ("unit_cost", models.DecimalField(decimal_places=2, max_digits=12)),
                ("line_total", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12)),
                (
                    "product",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="purchase_lines",
                        to="core.inventoryproduct",
                    ),
                ),
                (
                    "purchase",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="lines",
                        to="core.inventorypurchase",
                    ),
                ),
            ],
            options={
                "ordering": ["id"],
            },
        ),
    ]
