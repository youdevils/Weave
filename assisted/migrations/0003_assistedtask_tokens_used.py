from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('assisted', '0002_alter_assistedtask_failure_reason_code'),
    ]

    operations = [
        migrations.AddField(
            model_name='assistedtask',
            name='tokens_used',
            field=models.PositiveIntegerField(default=0),
        ),
    ]
