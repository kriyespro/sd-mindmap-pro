from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('teams', '0003_teaminvite_invited_username'),
    ]

    operations = [
        migrations.AddField(
            model_name='teammembership',
            name='is_active',
            field=models.BooleanField(default=True),
        ),
    ]
