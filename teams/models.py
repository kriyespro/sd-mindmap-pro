import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.text import slugify


class Team(models.Model):
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=80, unique=True, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='teams_created',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base = (slugify(self.name) or 'team')[:60]
            self.slug = base
            while Team.objects.filter(slug=self.slug).exclude(pk=self.pk).exists():
                self.slug = f'{base}-{uuid.uuid4().hex[:6]}'
        super().save(*args, **kwargs)


class TeamMembership(models.Model):
    ROLE_ADMIN = 'admin'
    ROLE_MEMBER = 'member'
    ROLE_CHOICES = (
        (ROLE_ADMIN, 'Admin'),
        (ROLE_MEMBER, 'Member'),
    )

    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='memberships')
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='team_memberships',
    )
    is_owner = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_MEMBER)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [['team', 'user']]
        ordering = ['-is_owner', 'joined_at']

    def __str__(self):
        return f'{self.user.username} @ {self.team.name}'

    @property
    def can_manage_invites(self) -> bool:
        return self.is_owner or self.role == self.ROLE_ADMIN


class TeamInvite(models.Model):
    ROLE_ADMIN = TeamMembership.ROLE_ADMIN
    ROLE_MEMBER = TeamMembership.ROLE_MEMBER
    ROLE_CHOICES = TeamMembership.ROLE_CHOICES

    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='invites')
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='team_invites_created',
    )
    email = models.EmailField(blank=True)
    invited_username = models.CharField(max_length=150, blank=True, default='', db_index=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_MEMBER)
    token = models.CharField(max_length=64, unique=True, db_index=True, editable=False)
    max_uses = models.PositiveIntegerField(default=1)
    use_count = models.PositiveIntegerField(default=0)
    expires_at = models.DateTimeField()
    is_revoked = models.BooleanField(default=False)
    accepted_at = models.DateTimeField(null=True, blank=True)
    accepted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='accepted_team_invites',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        who = self.invited_username or self.email or 'link-only'
        return f'Invite({self.team.name}, {who})'

    @staticmethod
    def new_token() -> str:
        return uuid.uuid4().hex + uuid.uuid4().hex

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = self.new_token()
        super().save(*args, **kwargs)

    @property
    def is_expired(self) -> bool:
        return self.expires_at <= timezone.now()

    @property
    def is_usable(self) -> bool:
        return not self.is_revoked and not self.is_expired and self.use_count < self.max_uses
