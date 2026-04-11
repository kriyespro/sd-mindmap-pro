"""Load demo user + sample OKR tree (personal workspace)."""

from datetime import date, timedelta

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction

from planner.models import Task


class Command(BaseCommand):
    help = 'Create user demo/demo1234 and a sample task hierarchy (idempotent).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Delete existing tasks authored by demo user before seeding.',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        user, created = User.objects.get_or_create(
            username='demo',
            defaults={'email': 'demo@example.com'},
        )
        user.set_password('demo1234')
        user.save()
        self.stdout.write(
            self.style.SUCCESS(
                f"User 'demo' {'created' if created else 'updated'} (password: demo1234)"
            )
        )

        if options['reset']:
            n, _ = Task.objects.filter(author=user, team__isnull=True).delete()
            self.stdout.write(self.style.WARNING(f'Removed {n} prior personal tasks.'))

        if Task.objects.filter(author=user, team__isnull=True).exists():
            self.stdout.write(self.style.NOTICE('Demo tasks already present — skip (use --reset to replace).'))
            return

        today = date.today()

        def mk(parent, title, **kw):
            return Task.objects.create(
                author=user,
                team=None,
                parent=parent,
                title=title,
                **kw,
            )

        root = mk(None, 'Development')
        tools = mk(root, 'Tools', due_date=today + timedelta(days=5))
        mk(tools, 'Lint & format CI', is_completed=True)
        mk(tools, 'Dependency audit', assignee_username='demo')

        sprints = mk(root, 'Sprints', due_date=today + timedelta(days=14))
        mk(sprints, 'Sprint planning template')
        cur = mk(sprints, 'Current sprint goals', due_date=today)
        mk(cur, 'Ship mind map polish', is_completed=True)
        mk(cur, 'Seed data & docs')

        auto = mk(root, 'Automation', due_date=today + timedelta(days=21))
        mk(auto, 'Tickets per user', due_date=today + timedelta(days=3))
        mk(auto, 'Trial signup flow')
        mk(auto, 'Grafana bar chart', assignee_username='demo')

        self.stdout.write(self.style.SUCCESS('Seeded personal OKR tree under Development.'))
