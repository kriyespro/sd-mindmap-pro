"""Backfill welcome tour projects for users who signed up before tutorial seeding existed."""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from users.services import seed_tutorial_for_user

User = get_user_model()


class Command(BaseCommand):
    help = 'Create Welcome Tour demo project for users who do not have one yet.'

    def handle(self, *args, **options):
        created = 0
        for user in User.objects.order_by('id'):
            project = seed_tutorial_for_user(user)
            if project:
                created += 1
                self.stdout.write(f'  {user.username} → {project.slug}')
        self.stdout.write(self.style.SUCCESS(f'Done. {created} user(s) processed.'))
