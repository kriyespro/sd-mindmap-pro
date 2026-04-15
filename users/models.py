from django.conf import settings
from django.db import models
from django.utils import timezone


class Profile(models.Model):
    TEAM_USER_LIMIT = 5
    TEAM_20_USER_LIMIT = 20

    PLAN_SOLO = 'solo'
    PLAN_TEAM = 'team'
    PLAN_TEAM_20 = 'team_20'
    PLAN_CHOICES = (
        (PLAN_SOLO, 'Solo'),
        (PLAN_TEAM, 'Team (up to 5 users)'),
        (PLAN_TEAM_20, 'Team Pro (up to 20 users)'),
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

    @classmethod
    def supports_team_plan(cls, plan: str) -> bool:
        return plan in {cls.PLAN_TEAM, cls.PLAN_TEAM_20}

    @classmethod
    def seat_limit_for_plan(cls, plan: str) -> int:
        if plan == cls.PLAN_TEAM_20:
            return cls.TEAM_20_USER_LIMIT
        if plan == cls.PLAN_TEAM:
            return cls.TEAM_USER_LIMIT
        return 1
