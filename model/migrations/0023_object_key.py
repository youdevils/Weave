from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('model', '0022_attributedefinition_key_unique'),
    ]

    operations = [
        migrations.AddField(
            model_name='object',
            name='key',
            field=models.SlugField(max_length=100, null=True),
        ),
    ]
