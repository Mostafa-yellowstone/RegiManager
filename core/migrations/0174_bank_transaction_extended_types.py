from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0173_membership_can_delete_vehicle"),
    ]

    operations = [
        migrations.AlterField(
            model_name="banktransaction",
            name="transaction_type",
            field=models.CharField(
                max_length=30,
                choices=[
                    ("income", "Income"),
                    ("expense", "Expense"),
                    ("income_credit_transfer", "Income + Credit Transfer"),
                    ("expense_debit_transfer", "Expenses + Debit Transfer"),
                    ("credit_transfer", "Credit Transfer"),
                    ("debit_transfer", "Debit Transfer"),
                ],
            ),
        ),
    ]
