# Merge agent portal with PSB license dates branch

from django.db import migrations


class Migration(migrations.Migration):
    """
    Empty join node for:
      - 0150_agent_portal
      - 0150_psb_license_dates
    """

    dependencies = [
        ("core", "0150_agent_portal"),
        ("core", "0150_psb_license_dates"),
    ]

    operations = []
