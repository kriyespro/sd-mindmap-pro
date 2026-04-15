from django.conf import settings
from django.db import models

from planner.crypto import decrypt_task_title, encrypt_task_title, is_task_title_encrypted


class Task(models.Model):
    team = models.ForeignKey(
        'teams.Team',
        on_delete=models.CASCADE,
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
    due_date = models.DateField(null=True, blank=True)
    assignee_username = models.CharField(max_length=150, blank=True)
    is_completed = models.BooleanField(default=False)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return self.title_plain[:80]

    @property
    def title_plain(self) -> str:
        return decrypt_task_title(self.title)

    def save(self, *args, **kwargs):
        title_in_memory = self.title or ''
        needs_encryption = bool(title_in_memory) and not is_task_title_encrypted(title_in_memory)
        if needs_encryption:
            self.title = encrypt_task_title(title_in_memory)
        super().save(*args, **kwargs)
        if needs_encryption:
            # Keep instance readable for downstream code paths in current request.
            self.title = title_in_memory


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
