from core.models import Organization
from django.utils.crypto import get_random_string

for org in Organization.objects.all():
    if not org.invite_code:
        while True:
            code = get_random_string(8).upper()
            if not Organization.objects.filter(invite_code=code).exists():
                org.invite_code = code
                org.save()
                print(f"Set code {code} for {org.name}")
                break
print("Done!")
