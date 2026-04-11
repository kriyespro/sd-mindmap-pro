from django.contrib import admin

from planner.models import Notification, Task


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ('title', 'team', 'author', 'parent', 'is_completed', 'due_date')
    list_filter = ('is_completed', 'team')
    search_fields = ('title', 'assignee_username')


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('user', 'message', 'is_read', 'created_at')
    list_filter = ('is_read',)
