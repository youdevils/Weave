from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('model', '0024_backfill_object_key'),
    ]

    operations = [
        migrations.AlterField(
            model_name='object',
            name='key',
            field=models.SlugField(max_length=100),
        ),
        migrations.AddConstraint(
            model_name='object',
            constraint=models.UniqueConstraint(
                fields=('model', 'object_type', 'key'),
                name='uniq_object_model_type_key',
            ),
        ),
    ]
