import uuid

from django.conf import settings
from django.db import models
from django.utils.text import slugify


class Project(models.Model):
    STATUS_PLANNING = 'planning'
    STATUS_ACTIVE = 'active'
    STATUS_ON_HOLD = 'on_hold'
    STATUS_COMPLETED = 'completed'
    STATUS_CANCELLED = 'cancelled'
    STATUS_CHOICES = [
        (STATUS_PLANNING, 'Planning'),
        (STATUS_ACTIVE, 'Active'),
        (STATUS_ON_HOLD, 'On Hold'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_CANCELLED, 'Cancelled'),
    ]

    PRIORITY_LOW = 'low'
    PRIORITY_MEDIUM = 'medium'
    PRIORITY_HIGH = 'high'
    PRIORITY_CRITICAL = 'critical'
    PRIORITY_CHOICES = [
        (PRIORITY_LOW, 'Low'),
        (PRIORITY_MEDIUM, 'Medium'),
        (PRIORITY_HIGH, 'High'),
        (PRIORITY_CRITICAL, 'Critical'),
    ]

    HEALTH_ON_TRACK = 'on_track'
    HEALTH_AT_RISK = 'at_risk'
    HEALTH_OFF_TRACK = 'off_track'
    HEALTH_CHOICES = [
        (HEALTH_ON_TRACK, 'On Track'),
        (HEALTH_AT_RISK, 'At Risk'),
        (HEALTH_OFF_TRACK, 'Off Track'),
    ]

    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=100, unique=True, db_index=True)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PLANNING)
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default=PRIORITY_MEDIUM)
    health = models.CharField(max_length=20, choices=HEALTH_CHOICES, default=HEALTH_ON_TRACK)

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='owned_projects',
    )
    team = models.ForeignKey(
        'teams.Team',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='projects',
    )
    client_name = models.CharField(max_length=200, blank=True)
    manager = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='managed_projects',
    )

    budget = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    progress = models.PositiveSmallIntegerField(default=0)

    is_archived = models.BooleanField(default=False)
    color = models.CharField(max_length=7, default='#6366f1')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name)[:80] or 'project'
            self.slug = base
            while Project.objects.filter(slug=self.slug).exclude(pk=self.pk).exists():
                self.slug = f'{base}-{uuid.uuid4().hex[:6]}'
        super().save(*args, **kwargs)

    @property
    def status_color(self):
        return {
            self.STATUS_PLANNING: 'blue',
            self.STATUS_ACTIVE: 'green',
            self.STATUS_ON_HOLD: 'yellow',
            self.STATUS_COMPLETED: 'emerald',
            self.STATUS_CANCELLED: 'red',
        }.get(self.status, 'gray')

    @property
    def priority_color(self):
        return {
            self.PRIORITY_LOW: 'slate',
            self.PRIORITY_MEDIUM: 'blue',
            self.PRIORITY_HIGH: 'orange',
            self.PRIORITY_CRITICAL: 'red',
        }.get(self.priority, 'gray')

    @property
    def health_color(self):
        return {
            self.HEALTH_ON_TRACK: 'green',
            self.HEALTH_AT_RISK: 'yellow',
            self.HEALTH_OFF_TRACK: 'red',
        }.get(self.health, 'gray')


class ProjectMember(models.Model):
    ROLE_OWNER = 'owner'
    ROLE_MANAGER = 'manager'
    ROLE_MEMBER = 'member'
    ROLE_VIEWER = 'viewer'
    ROLE_CHOICES = [
        (ROLE_OWNER, 'Owner'),
        (ROLE_MANAGER, 'Manager'),
        (ROLE_MEMBER, 'Member'),
        (ROLE_VIEWER, 'Viewer'),
    ]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='members')
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='project_memberships',
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_MEMBER)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [['project', 'user']]
        ordering = ['role', 'joined_at']

    def __str__(self):
        return f'{self.user.username} → {self.project.name} ({self.role})'
