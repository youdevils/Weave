from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("assisted", "0005_staged_workflow_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="assistedtask",
            name="completeness",
            field=models.CharField(blank=True, max_length=10),
        ),
    ]
