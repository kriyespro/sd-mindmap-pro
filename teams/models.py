import uuid

from django.conf import settings
from django.db import models
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
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='memberships')
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='team_memberships',
    )
    is_owner = models.BooleanField(default=False)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [['team', 'user']]
        ordering = ['-is_owner', 'joined_at']

    def __str__(self):
        return f'{self.user.username} @ {self.team.name}'
