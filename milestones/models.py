from django.conf import settings
from django.db import models


class Milestone(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_IN_PROGRESS = 'in_progress'
    STATUS_COMPLETED = 'completed'
    STATUS_MISSED = 'missed'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_IN_PROGRESS, 'In Progress'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_MISSED, 'Missed'),
    ]

    project = models.ForeignKey(
        'projects.Project',
        on_delete=models.CASCADE,
        related_name='milestones',
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    due_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    progress = models.PositiveSmallIntegerField(default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_milestones',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['due_date']

    def __str__(self):
        return self.name

    @property
    def is_overdue(self):
        from django.utils import timezone
        return self.due_date < timezone.now().date() and self.status != self.STATUS_COMPLETED

    @property
    def status_color(self):
        return {
            self.STATUS_PENDING: 'slate',
            self.STATUS_IN_PROGRESS: 'blue',
            self.STATUS_COMPLETED: 'green',
            self.STATUS_MISSED: 'red',
        }.get(self.status, 'slate')


class MilestoneTask(models.Model):
    """Link tasks to milestones."""
    milestone = models.ForeignKey(Milestone, on_delete=models.CASCADE, related_name='linked_tasks')
    task = models.ForeignKey('planner.Task', on_delete=models.CASCADE, related_name='milestones')

    class Meta:
        unique_together = [['milestone', 'task']]

    def __str__(self):
        return f'{self.task_id} → {self.milestone.name}'
