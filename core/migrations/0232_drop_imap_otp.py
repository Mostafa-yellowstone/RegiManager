from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0231_quote_engine_job"),
    ]

    operations = [
        migrations.RemoveField(model_name="carriercredential", name="otp_imap_host"),
        migrations.RemoveField(model_name="carriercredential", name="otp_imap_password_enc"),
        migrations.RemoveField(model_name="carriercredential", name="otp_sender_hints"),
        migrations.AlterField(
            model_name="carriercredential",
            name="otp_email",
            field=models.EmailField(
                blank=True,
                default="",
                help_text="Display only. Where the carrier sends the login code. A person types the code on the run page; nothing reads this mailbox.",
                max_length=254,
            ),
        ),
    ]
