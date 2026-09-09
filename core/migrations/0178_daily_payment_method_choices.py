from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0177_quote_lead_dealer_referral_split"),
    ]

    operations = [
        migrations.AlterField(
            model_name="dailypaymenttransaction",
            name="payment_method",
            field=models.CharField(
                choices=[
                    ("cash", "Cash"),
                    ("zelle", "Zelle"),
                    ("credit_card", "Credit Card"),
                    ("checks", "Checks"),
                    ("payment_hub", "Payment Hub"),
                ],
                max_length=20,
            ),
        ),
    ]
