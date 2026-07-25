# Generated manually for agent portal

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("core", "0150_psb_license_dates"),
    ]

    operations = [
        migrations.AddField(
            model_name="organizationmembership",
            name="can_assign_agent_tasks",
            field=models.BooleanField(
                default=False,
                help_text="Lead agents: can create and assign portal checklist tasks to other agents.",
            ),
        ),
        migrations.AddField(
            model_name="organizationmembership",
            name="profile_photo",
            field=models.ImageField(
                blank=True,
                help_text="Agent profile photo shown on the agent portal home.",
                null=True,
                upload_to="agent_profiles/",
            ),
        ),
        migrations.CreateModel(
            name="AgentActivityEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("domain", models.CharField(choices=[("insurance", "Insurance"), ("motorclub", "Motor Club"), ("tlc", "TLC")], db_index=True, max_length=20)),
                ("event_type", models.CharField(choices=[("quote_created", "Quote created"), ("policy_bound", "Policy bound"), ("endorsement", "Endorsement"), ("membership_created", "Membership created"), ("membership_updated", "Membership updated"), ("tlc_policy_created", "TLC policy created"), ("tlc_policy_updated", "TLC policy updated"), ("tlc_endorsement", "TLC endorsement"), ("other", "Other")], db_index=True, max_length=40)),
                ("title", models.CharField(max_length=200)),
                ("detail", models.CharField(blank=True, default="", max_length=400)),
                ("object_id", models.PositiveIntegerField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("actor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="agent_activity_events", to=settings.AUTH_USER_MODEL)),
                ("membership", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="activity_events", to="core.organizationmembership")),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="agent_activity_events", to="core.organization")),
            ],
            options={
                "verbose_name": "Agent activity event",
                "verbose_name_plural": "Agent activity events",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="AgentAttendanceSession",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("work_date", models.DateField(db_index=True, help_text="Cairo calendar date this shift belongs to.")),
                ("opened_at", models.DateTimeField()),
                ("closed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("membership", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="attendance_sessions", to="core.organizationmembership")),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="agent_attendance_sessions", to="core.organization")),
            ],
            options={
                "verbose_name": "Agent attendance session",
                "verbose_name_plural": "Agent attendance sessions",
                "ordering": ["-work_date", "-opened_at"],
            },
        ),
        migrations.CreateModel(
            name="AgentTask",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=200)),
                ("description", models.TextField(blank=True, default="")),
                ("is_done", models.BooleanField(db_index=True, default=False)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("due_date", models.DateField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("assigned_to", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="assigned_tasks", to="core.organizationmembership")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="agent_tasks_created", to=settings.AUTH_USER_MODEL)),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="agent_tasks", to="core.organization")),
            ],
            options={
                "verbose_name": "Agent task",
                "verbose_name_plural": "Agent tasks",
                "ordering": ["is_done", "-created_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="agentattendancesession",
            constraint=models.UniqueConstraint(fields=("membership", "work_date"), name="uniq_agent_attendance_membership_work_date"),
        ),
        migrations.AddIndex(
            model_name="agentactivityevent",
            index=models.Index(fields=["organization", "actor", "-created_at"], name="core_agenta_organiz_7f2c1a_idx"),
        ),
    ]
