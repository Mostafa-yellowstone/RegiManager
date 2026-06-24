from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0129_remove_organizationmembership_profile_photo"),
    ]

    operations = [
        migrations.AddField(
            model_name="organizationmembership",
            name="can_issue_refund",
            field=models.BooleanField(
                default=False,
                help_text="Can this agent issue refunds from vehicle transaction history?",
            ),
        ),
        migrations.AddField(
            model_name="servicerecord",
            name="refunded_from",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="refund_entries",
                to="core.servicerecord",
            ),
        ),
        migrations.AlterField(
            model_name="servicerecord",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("completed", "Completed"),
                    ("failed", "Failed"),
                    ("refund", "Refund"),
                ],
                db_index=True,
                default="pending",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="servicerecordpayment",
            name="entry_type",
            field=models.CharField(
                choices=[
                    ("opening", "Opening transaction"),
                    ("payment", "Payment"),
                    ("refund", "Refund"),
                ],
                default="payment",
                max_length=20,
            ),
        ),
    ]
