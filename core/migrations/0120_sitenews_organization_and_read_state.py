import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0119_organization_is_public_intake_enabled"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="sitenews",
            name="organization",
            field=models.ForeignKey(
                blank=True,
                help_text="PSB this announcement belongs to. Leave blank for legacy global posts.",
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="site_news",
                to="core.organization",
            ),
        ),
        migrations.AddField(
            model_name="sitenews",
            name="published_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="published_site_news",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.CreateModel(
            name="SiteNewsRead",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("read_at", models.DateTimeField(auto_now_add=True)),
                (
                    "news",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="reads", to="core.sitenews"),
                ),
                (
                    "user",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="site_news_reads", to=settings.AUTH_USER_MODEL),
                ),
            ],
            options={
                "indexes": [models.Index(fields=["user", "news"], name="core_sitene_user_id_6f0a8b_idx")],
                "unique_together": {("user", "news")},
            },
        ),
    ]
