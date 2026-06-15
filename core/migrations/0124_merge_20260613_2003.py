# Server merge migration (June 13, 2026). Kept as a no-op leaf so deploys
# share the same graph as the production VPS before state-specific DMV work.
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0123_organization_email"),
    ]

    operations = []
