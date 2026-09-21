from django.db import migrations, models


class Migration(migrations.Migration):
    """Indexes that speed Pulse owner insurance + DMV period queries."""

    dependencies = [
        ("core", "0191_clientintake_separate_referral_dealer"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="insurancepolicy",
            index=models.Index(
                fields=["organization", "stage", "bound_date"],
                name="core_inspol_org_stage_bound_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="insurancepolicy",
            index=models.Index(
                fields=["organization", "stage", "status"],
                name="core_inspol_org_stage_stat_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="insurancepolicy",
            index=models.Index(
                fields=["organization", "insurance_company", "stage"],
                name="core_inspol_org_co_stage_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="banktransaction",
            index=models.Index(
                fields=["bank_account", "date"],
                name="core_banktx_acct_date_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="servicerecord",
            index=models.Index(
                fields=["organization", "transaction_date"],
                name="core_svcrec_org_txdate_idx",
            ),
        ),
    ]
