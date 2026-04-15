from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('teams', '0002_teammembership_role_teaminvite'),
    ]

    operations = [
        migrations.AddField(
            model_name='teaminvite',
            name='invited_username',
            field=models.CharField(blank=True, db_index=True, default='', max_length=150),
        ),
    ]
