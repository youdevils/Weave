from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ai", "0002_staged_workflow_steps"),
    ]

    operations = [
        migrations.AddField(
            model_name="aiexecutionstep",
            name="sequence",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="aiexecutionstep",
            name="provider_call",
            field=models.BooleanField(default=True),
        ),
        migrations.AlterModelOptions(
            name="aiexecutionstep",
            options={"ordering": ["execution", "sequence", "call_index"]},
        ),
    ]
