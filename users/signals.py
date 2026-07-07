from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from users.models import Profile

User = get_user_model()


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.get_or_create(
            user=instance,
            defaults={
                'is_trial': True,
                'trial_ends': timezone.localdate() + timedelta(days=7),
            },
        )
        user_id = instance.pk

        def _seed_tutorial():
            from django.contrib.auth import get_user_model
            from users.services import seed_tutorial_for_user

            user = get_user_model().objects.filter(pk=user_id).first()
            if user:
                seed_tutorial_for_user(user)

        transaction.on_commit(_seed_tutorial)
