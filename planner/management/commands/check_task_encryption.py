from django.core.management.base import BaseCommand, CommandError

from planner.crypto import decrypt_task_title, encrypt_task_title, is_task_title_encrypted
from planner.models import Task


class Command(BaseCommand):
    help = 'Verify task-title encryption roundtrip and list broken titles.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--delete-broken',
            action='store_true',
            help='Delete tasks whose titles fail to decrypt with the current key.',
        )

    def handle(self, *args, **options):
        sample = 'encryption-self-test-99D'
        token = encrypt_task_title(sample)
        plain = decrypt_task_title(token)
        if plain != sample:
            raise CommandError(
                f'Encryption roundtrip FAILED (got {plain!r}). '
                'Check SECRET_KEY / TASK_ENCRYPTION_KEY — do not use duplicate SECRET_KEY lines in .env.'
            )
        self.stdout.write(self.style.SUCCESS('Roundtrip OK: encrypt → decrypt works with current key.'))

        from django.conf import settings

        self.stdout.write(f'SECRET_KEY prefix: {(settings.SECRET_KEY or "")[:20]}...')
        self.stdout.write(
            f'TASK_ENCRYPTION_KEY set: {bool((getattr(settings, "TASK_ENCRYPTION_KEY", "") or "").strip())}'
        )

        broken_ids: list[int] = []
        ok = 0
        for task_id, raw in Task.objects.values_list('id', 'title'):
            if not raw:
                continue
            if is_task_title_encrypted(raw) and decrypt_task_title(raw) == '[DECRYPTION_FAILED]':
                broken_ids.append(task_id)
            else:
                ok += 1

        self.stdout.write(f'Tasks OK: {ok}')
        self.stdout.write(f'Tasks broken: {len(broken_ids)}')
        if broken_ids:
            self.stdout.write(f'Broken ids: {broken_ids[:50]}')

        if options['delete_broken']:
            deleted, _ = Task.objects.filter(id__in=broken_ids).delete()
            self.stdout.write(self.style.WARNING(f'Deleted objects: {deleted}'))
        elif broken_ids:
            self.stdout.write('Re-run with --delete-broken to remove unreadable tasks.')
