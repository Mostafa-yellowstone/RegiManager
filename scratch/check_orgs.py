import os
import sys
import django

sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'RegiManager.settings')
django.setup()

from django.contrib.auth.models import User
from core.models import OrganizationMembership

users = User.objects.all()
for user in users:
    memberships = OrganizationMembership.objects.filter(user=user)
    print(f"User: {user.username}")
    for m in memberships:
        print(f"  Org: {m.organization.name} (Role: {m.role}, Active: {m.is_active})")
