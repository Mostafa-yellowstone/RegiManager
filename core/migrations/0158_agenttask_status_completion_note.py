from django.db import migrations, models


def forwards_sync_status(apps, schema_editor):
    AgentTask = apps.get_model("core", "AgentTask")
    AgentTask.objects.filter(is_done=True).update(status="done")
    AgentTask.objects.filter(is_done=False).exclude(status="todo").update(status="todo")


def backwards_noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0157_emailmarketingcontact_assignment"),
    ]

    operations = [
        migrations.AddField(
            model_name="agenttask",
            name="status",
            field=models.CharField(
                choices=[
                    ("todo", "To do"),
                    ("in_progress", "In progress"),
                    ("waiting", "Waiting"),
                    ("done", "Done"),
                ],
                db_index=True,
                default="todo",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="agenttask",
            name="completion_note",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.RunPython(forwards_sync_status, backwards_noop),
    ]
