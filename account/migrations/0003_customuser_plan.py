from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('account', '0002_customuser_assisted_tier'),
    ]

    operations = [
        migrations.AddField(
            model_name='customuser',
            name='plan',
            field=models.CharField(
                choices=[
                    ('learner', 'Learner'),
                    ('communicator', 'Communicator'),
                    ('collaborator', 'Collaborator'),
                ],
                default='learner',
                max_length=20,
            ),
        ),
    ]
