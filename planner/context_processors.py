from __future__ import annotations

from typing import Any

from django.db.models import Exists, OuterRef, Q

from planner.models import Notification
from planner.models import Task
from teams.models import TeamMembership


def workspace_chrome(request: Any) -> dict[str, Any]:
    if not getattr(request, 'user', None) or not request.user.is_authenticated:
        return {}
    layout = request.session.get('task_layout', 'mindmap')
    if layout not in ('tree', 'mindmap'):
        layout = 'mindmap'
    team_tasks = Task.objects.filter(team_id=OuterRef('team_id'))
    active_tasks = team_tasks.filter(is_archived=False)
    return {
        'team_memberships': (
            TeamMembership.objects.filter(user=request.user, is_active=True)
            .annotate(has_any_tasks=Exists(team_tasks))
            .annotate(has_active_tasks=Exists(active_tasks))
            .filter(Q(has_active_tasks=True) | Q(has_any_tasks=False))
            .select_related('team')
            .order_by('-is_pinned', 'pinned_at', 'team__name')
        ),
        'notifications': Notification.objects.filter(
            user=request.user, is_read=False
        )[:30],
        'task_layout': layout,
    }
