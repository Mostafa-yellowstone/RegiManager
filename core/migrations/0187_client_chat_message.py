from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("core", "0186_daily_payment_broker_fee"),
    ]

    operations = [
        migrations.CreateModel(
            name="ClientChatMessage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "sender_role",
                    models.CharField(
                        choices=[("client", "Client"), ("staff", "Staff")],
                        db_index=True,
                        max_length=12,
                    ),
                ),
                ("body", models.TextField()),
                ("is_read_by_staff", models.BooleanField(db_index=True, default=False)),
                ("is_read_by_client", models.BooleanField(db_index=True, default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    "client",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="chat_messages",
                        to="core.client",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="client_chat_messages",
                        to="core.organization",
                    ),
                ),
                (
                    "staff_user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="client_chat_messages_sent",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="clientchatmessage",
            index=models.Index(fields=["client", "created_at"], name="core_client_client__7a2e1a_idx"),
        ),
        migrations.AddIndex(
            model_name="clientchatmessage",
            index=models.Index(fields=["client", "is_read_by_staff"], name="core_client_client__b8c1d2_idx"),
        ),
    ]
