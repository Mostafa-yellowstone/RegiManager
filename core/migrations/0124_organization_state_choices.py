from django.db import migrations, models

US_STATES = [
    ("AL", "Alabama"), ("AK", "Alaska"), ("AZ", "Arizona"), ("AR", "Arkansas"), ("CA", "California"),
    ("CO", "Colorado"), ("CT", "Connecticut"), ("DE", "Delaware"), ("FL", "Florida"), ("GA", "Georgia"),
    ("HI", "Hawaii"), ("ID", "Idaho"), ("IL", "Illinois"), ("IN", "Indiana"), ("IA", "Iowa"),
    ("KS", "Kansas"), ("KY", "Kentucky"), ("LA", "Louisiana"), ("ME", "Maine"), ("MD", "Maryland"),
    ("MA", "Massachusetts"), ("MI", "Michigan"), ("MN", "Minnesota"), ("MS", "Mississippi"), ("MO", "Missouri"),
    ("MT", "Montana"), ("NE", "Nebraska"), ("NV", "Nevada"), ("NH", "New Hampshire"), ("NJ", "New Jersey"),
    ("NM", "New Mexico"), ("NY", "New York"), ("NC", "North Carolina"), ("ND", "North Dakota"), ("OH", "Ohio"),
    ("OK", "Oklahoma"), ("OR", "Oregon"), ("PA", "Pennsylvania"), ("RI", "Rhode Island"), ("SC", "South Carolina"),
    ("SD", "South Dakota"), ("TN", "Tennessee"), ("TX", "Texas"), ("UT", "Utah"), ("VT", "Vermont"),
    ("VA", "Virginia"), ("WA", "Washington"), ("WV", "West Virginia"), ("WI", "Wisconsin"), ("WY", "Wyoming"),
]


def normalize_organization_states(apps, schema_editor):
    Organization = apps.get_model("core", "Organization")
    codes = {code for code, _ in US_STATES}
    name_to_code = {name.upper(): code for code, name in US_STATES}

    for org in Organization.objects.all().iterator():
        raw = (org.state or "").strip().upper()
        if raw in codes:
            normalized = raw
        elif raw in name_to_code:
            normalized = name_to_code[raw]
        elif len(raw) == 2:
            normalized = raw if raw in codes else "NY"
        else:
            normalized = "NY"
        if org.state != normalized:
            org.state = normalized
            org.save(update_fields=["state"])


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0123_organization_email"),
    ]

    operations = [
        migrations.RunPython(normalize_organization_states, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="organization",
            name="state",
            field=models.CharField(
                blank=True,
                choices=US_STATES,
                default="NY",
                help_text="Motor vehicle state for this PSB. Vehicle profiles show DMV forms for this state.",
                max_length=2,
            ),
        ),
    ]
