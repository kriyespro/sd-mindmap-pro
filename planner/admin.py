from django.contrib import admin

from planner.models import Notification, Task


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'masked_title',
        'team',
        'author',
        'parent',
        'is_completed',
        'due_date',
    )
    list_filter = ('is_completed', 'team')
    search_fields = ('author__username', 'team__name')
    readonly_fields = ('masked_title', 'masked_assignee', 'team', 'author', 'parent', 'is_completed', 'due_date')
    fields = ('masked_title', 'masked_assignee', 'team', 'author', 'parent', 'is_completed', 'due_date')

    @admin.display(description='Title')
    def masked_title(self, obj):
        return '[ENCRYPTED]'

    @admin.display(description='Assignee')
    def masked_assignee(self, obj):
        return '[ENCRYPTED]' if obj.assignee_username else '-'

    def has_add_permission(self, request):
        return False


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('user', 'message', 'is_read', 'created_at')
    list_filter = ('is_read',)
