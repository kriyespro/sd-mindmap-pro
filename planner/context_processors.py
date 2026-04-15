from __future__ import annotations

from typing import Any

from planner.models import Notification
from teams.models import TeamMembership


def workspace_chrome(request: Any) -> dict[str, Any]:
    if not getattr(request, 'user', None) or not request.user.is_authenticated:
        return {}
    layout = request.session.get('task_layout', 'mindmap')
    if layout not in ('tree', 'mindmap'):
        layout = 'mindmap'
    return {
        'team_memberships': (
            TeamMembership.objects.filter(user=request.user, is_active=True)
            .select_related('team')
            .order_by('team__name')
        ),
        'notifications': Notification.objects.filter(
            user=request.user, is_read=False
        )[:30],
        'task_layout': layout,
    }
