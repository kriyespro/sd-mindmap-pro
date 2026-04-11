from django.conf import settings
from django.db import models
from django.utils import timezone


class Profile(models.Model):
    TEAM_USER_LIMIT = 5

    PLAN_SOLO = 'solo'
    PLAN_TEAM = 'team'
    PLAN_CHOICES = (
        (PLAN_SOLO, 'Solo'),
        (PLAN_TEAM, 'Team (up to 5 users)'),
    )

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='profile',
    )
    plan = models.CharField(
        max_length=20,
        choices=PLAN_CHOICES,
        default=PLAN_SOLO,
        help_text='Active subscription plan.',
    )
    is_trial = models.BooleanField(
        default=True,
        help_text='Trial access; manage from admin actions or inline.',
    )
    trial_ends = models.DateField(
        null=True,
        blank=True,
        help_text='Last day of 7-day trial (inclusive).',
    )

    class Meta:
        verbose_name = 'profile'
        verbose_name_plural = 'profiles'

    def __str__(self) -> str:
        return f'Profile({self.user.username})'

    @property
    def trial_active(self) -> bool:
        if not self.is_trial or not self.trial_ends:
            return False
        return self.trial_ends >= timezone.localdate()
