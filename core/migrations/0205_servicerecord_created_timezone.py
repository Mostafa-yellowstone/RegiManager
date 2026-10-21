from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0204_insurance_producers'),
    ]

    operations = [
        migrations.AddField(
            model_name='servicerecord',
            name='created_timezone',
            field=models.CharField(blank=True, default='', help_text='IANA timezone of the device that recorded the transaction (e.g. America/New_York, Africa/Cairo).', max_length=64),
        ),
    ]
