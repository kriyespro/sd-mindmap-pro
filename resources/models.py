from django.conf import settings
from django.db import models


class ResourceAllocation(models.Model):
    ROLE_CHOICES = [
        ('pm', 'Project Manager'),
        ('dev', 'Developer'),
        ('design', 'Designer'),
        ('qa', 'QA Engineer'),
        ('devops', 'DevOps'),
        ('analyst', 'Analyst'),
        ('other', 'Other'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='allocations')
    project = models.ForeignKey('projects.Project', on_delete=models.CASCADE, related_name='allocations', null=True, blank=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='dev')
    hours_per_day = models.DecimalField(max_digits=4, decimal_places=1, default=8.0)
    start_date = models.DateField()
    end_date = models.DateField()
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='created_allocations')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['start_date', 'user__username']

    def __str__(self):
        proj = self.project.name if self.project else 'No project'
        return f'{self.user.username} on {proj} ({self.hours_per_day}h/day)'

    @property
    def total_hours(self):
        if self.start_date and self.end_date:
            delta = (self.end_date - self.start_date).days + 1
            return float(self.hours_per_day) * delta
        return 0
