from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('account', '0004_backfill_plan_from_assisted_tier'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='customuser',
            name='assisted_tier',
        ),
    ]
