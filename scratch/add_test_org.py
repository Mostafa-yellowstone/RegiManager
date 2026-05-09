import os
import sys
import django

sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'RegiManager.settings')
django.setup()

from django.contrib.auth.models import User
from core.models import Organization, OrganizationMembership

user = User.objects.filter(username='sam').first()
if user:
    # Create a second location
    org2, created = Organization.objects.get_or_create(
        name="Branch Office - Brooklyn",
        city="Brooklyn",
        state="NY",
        defaults={'address_line': '456 Second St'}
    )
    
    # Add sam as owner
    membership, created = OrganizationMembership.objects.get_or_create(
        organization=org2,
        user=user,
        defaults={'role': OrganizationMembership.Role.OWNER}
    )
    
    print(f"Added {user.username} to {org2.name}")
else:
    print("User 'sam' not found")
