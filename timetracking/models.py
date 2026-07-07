from django.conf import settings
from django.db import models
from django.utils import timezone


class TimeEntry(models.Model):
    STATUS_RUNNING = 'running'
    STATUS_PAUSED = 'paused'
    STATUS_STOPPED = 'stopped'
    STATUS_CHOICES = [
        (STATUS_RUNNING, 'Running'),
        (STATUS_PAUSED, 'Paused'),
        (STATUS_STOPPED, 'Stopped'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='time_entries')
    task = models.ForeignKey(
        'planner.Task', null=True, blank=True, on_delete=models.SET_NULL, related_name='time_entries'
    )
    project = models.ForeignKey(
        'projects.Project', null=True, blank=True, on_delete=models.SET_NULL, related_name='time_entries'
    )
    description = models.CharField(max_length=500, blank=True)
    started_at = models.DateTimeField(default=timezone.now)
    stopped_at = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_STOPPED)
    is_approved = models.BooleanField(default=False)

    class Meta:
        ordering = ['-started_at']

    def __str__(self):
        return f'{self.user.username} — {self.description or "no desc"} ({self.duration_seconds}s)'

    def stop(self):
        if self.status == self.STATUS_RUNNING:
            now = timezone.now()
            elapsed = int((now - self.started_at).total_seconds())
            self.duration_seconds += elapsed
            self.stopped_at = now
            self.status = self.STATUS_STOPPED
            self.save(update_fields=['duration_seconds', 'stopped_at', 'status'])

    @property
    def hours(self) -> float:
        return round(self.duration_seconds / 3600, 2)

    @property
    def formatted(self) -> str:
        h = self.duration_seconds // 3600
        m = (self.duration_seconds % 3600) // 60
        s = self.duration_seconds % 60
        return f'{h:02d}:{m:02d}:{s:02d}'
