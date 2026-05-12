from core.models import ServiceRecord
count = 0
for sr in ServiceRecord.objects.filter(referral__isnull=True, referral_balance__gt=0):
    if sr.vehicle and sr.vehicle.client.referral:
        sr.referral = sr.vehicle.client.referral
        sr.save()
        count += 1
print(f"Successfully linked {count} records to their referrals.")
