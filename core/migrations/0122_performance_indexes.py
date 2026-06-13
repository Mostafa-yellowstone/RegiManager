# Generated migration for audit performance indexes

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0121_referral_fee_and_commission"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="clientintake",
            index=models.Index(
                fields=["organization", "status", "-created_at"],
                name="core_intake_org_status_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="servicerecord",
            index=models.Index(
                fields=["is_referral_paid", "referral"],
                name="core_svc_ref_unpaid_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="servicerecord",
            index=models.Index(
                fields=["organization", "is_referral_paid"],
                name="core_svc_org_unpaid_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="insurancepolicy",
            index=models.Index(
                fields=["organization", "client"],
                name="core_ins_org_client_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="insurancepolicy",
            index=models.Index(
                fields=["organization", "status", "-created_at"],
                name="core_ins_org_status_idx",
            ),
        ),
    ]
