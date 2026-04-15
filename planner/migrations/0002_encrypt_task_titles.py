import base64
import hashlib

from cryptography.fernet import Fernet
from django.conf import settings
from django.db import migrations, models


TITLE_PREFIX = 'encv1:'


def _fernet_key() -> bytes:
    configured = (getattr(settings, 'TASK_ENCRYPTION_KEY', '') or '').strip()
    if configured:
        return configured.encode('utf-8')
    digest = hashlib.sha256(settings.SECRET_KEY.encode('utf-8')).digest()
    return base64.urlsafe_b64encode(digest)


def encrypt_existing_titles(apps, schema_editor):
    Task = apps.get_model('planner', 'Task')
    fernet = Fernet(_fernet_key())
    for task in Task.objects.all().only('id', 'title'):
        raw = (task.title or '').strip()
        if not raw or raw.startswith(TITLE_PREFIX):
            continue
        token = fernet.encrypt(raw.encode('utf-8')).decode('utf-8')
        task.title = f'{TITLE_PREFIX}{token}'
        task.save(update_fields=['title'])


class Migration(migrations.Migration):
    dependencies = [
        ('planner', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='task',
            name='title',
            field=models.TextField(),
        ),
        migrations.RunPython(encrypt_existing_titles, migrations.RunPython.noop),
    ]
