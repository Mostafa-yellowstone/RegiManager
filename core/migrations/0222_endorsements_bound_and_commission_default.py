from decimal import Decimal

from django.db import migrations

OLD_DEFAULT = Decimal("15.00")
NEW_DEFAULT = Decimal("10.00")


def forwards(apps, schema_editor):
    from core.insurance_commissions import calculate_unearned_commission
    from core.insurance_producers import producer_total_for_policy

    InsurancePolicy = apps.get_model("core", "InsurancePolicy")
    InsurancePolicy.objects.filter(stage="endorsement").update(stage="bound")

    for policy in InsurancePolicy.objects.filter(commission_rate=OLD_DEFAULT).iterator():
        policy.commission_rate = NEW_DEFAULT
        premium = Decimal(str(policy.premium or 0))
        policy.commission_amount = premium * NEW_DEFAULT / Decimal("100.00") if premium > 0 else None
        if policy.status == "inactive":
            policy.unearned_commission = calculate_unearned_commission(
                policy.commission_amount,
                policy.start_date,
                policy.end_date,
                policy.inactive_date,
                insurance_period_months=policy.insurance_period_months,
                premium=policy.premium,
                commission_rate=policy.commission_rate,
            )
        policy.producer_commission_amount = producer_total_for_policy(policy)
        InsurancePolicy.objects.filter(pk=policy.pk).update(
            commission_rate=policy.commission_rate,
            commission_amount=policy.commission_amount,
            unearned_commission=policy.unearned_commission,
            producer_commission_amount=policy.producer_commission_amount,
        )


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0221_insurance_wholesalers"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
