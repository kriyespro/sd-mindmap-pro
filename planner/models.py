from django.conf import settings
from django.db import models

from planner.crypto import decrypt_task_title, encrypt_task_title, is_task_title_encrypted


class Task(models.Model):
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

    STATUS_TODO = 'todo'
    STATUS_IN_PROGRESS = 'in_progress'
    STATUS_REVIEW = 'review'
    STATUS_TESTING = 'testing'
    STATUS_DONE = 'done'
    STATUS_CHOICES = [
        (STATUS_TODO, 'To Do'),
        (STATUS_IN_PROGRESS, 'In Progress'),
        (STATUS_REVIEW, 'Review'),
        (STATUS_TESTING, 'Testing'),
        (STATUS_DONE, 'Done'),
    ]

    team = models.ForeignKey(
        'teams.Team',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='tasks',
    )
    project = models.ForeignKey(
        'projects.Project',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='tasks',
    )
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='children',
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='authored_tasks',
    )
    title = models.TextField()
    description = models.TextField(blank=True)
    due_date = models.DateField(null=True, blank=True)
    start_date = models.DateField(null=True, blank=True)
    assignee_username = models.CharField(max_length=150, blank=True)
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default=PRIORITY_MEDIUM)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_TODO)
    tags = models.CharField(max_length=500, blank=True)
    estimated_hours = models.DecimalField(max_digits=6, decimal_places=1, null=True, blank=True)
    is_completed = models.BooleanField(default=False)
    is_archived = models.BooleanField(default=False)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['position', 'id']

    def __str__(self):
        return self.title_plain[:80]

    @property
    def title_plain(self) -> str:
        return decrypt_task_title(self.title)

    @property
    def tags_list(self) -> list:
        return [t.strip() for t in self.tags.split(',') if t.strip()] if self.tags else []

    @property
    def priority_color(self):
        return {
            self.PRIORITY_LOW: 'slate',
            self.PRIORITY_MEDIUM: 'blue',
            self.PRIORITY_HIGH: 'orange',
            self.PRIORITY_CRITICAL: 'red',
        }.get(self.priority, 'gray')

    @property
    def status_color(self):
        return {
            self.STATUS_TODO: 'slate',
            self.STATUS_IN_PROGRESS: 'blue',
            self.STATUS_REVIEW: 'purple',
            self.STATUS_TESTING: 'orange',
            self.STATUS_DONE: 'green',
        }.get(self.status, 'gray')

    def save(self, *args, **kwargs):
        title_in_memory = self.title or ''
        needs_encryption = bool(title_in_memory) and not is_task_title_encrypted(title_in_memory)
        if needs_encryption:
            self.title = encrypt_task_title(title_in_memory)
        super().save(*args, **kwargs)
        if needs_encryption:
            # Keep instance readable for downstream code paths in current request.
            self.title = title_in_memory


class TaskComment(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='task_comments')
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f'Comment by {self.author.username} on task {self.task_id}'


class TaskChecklist(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='checklist_items')
    text = models.CharField(max_length=500)
    is_done = models.BooleanField(default=False)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['position', 'id']

    def __str__(self):
        return self.text[:80]


class TaskWatcher(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='watchers')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='watched_tasks')
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [['task', 'user']]

    def __str__(self):
        return f'{self.user.username} watching task {self.task_id}'


class Notification(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications',
    )
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.message[:60]
