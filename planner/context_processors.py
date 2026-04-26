from __future__ import annotations

from typing import Any

from django.db.models import Exists, OuterRef, Q

from planner.models import Notification
from planner.models import Task
from planner.services import tasks_for_workspace, workspace_root_average_percent
from teams.models import TeamMembership


def workspace_chrome(request: Any) -> dict[str, Any]:
    if not getattr(request, 'user', None) or not request.user.is_authenticated:
        return {}
    layout = request.session.get('task_layout', 'mindmap')
    if layout not in ('tree', 'mindmap'):
        layout = 'mindmap'
    team_tasks = Task.objects.filter(team_id=OuterRef('team_id'))
    active_tasks = team_tasks.filter(is_archived=False)
    memberships = list(
        TeamMembership.objects.filter(user=request.user, is_active=True)
        .annotate(has_any_tasks=Exists(team_tasks))
        .annotate(has_active_tasks=Exists(active_tasks))
        .filter(Q(has_active_tasks=True) | Q(has_any_tasks=False))
        .select_related('team')
        .order_by('-is_pinned', 'pinned_at', 'team__name')
    )
    for m in memberships:
        team_qs = tasks_for_workspace(request.user, m.team)
        setattr(m, 'done_pct', workspace_root_average_percent(team_qs))

    my_teams = [m for m in memberships if bool(m.is_owner)]
    other_teams = [m for m in memberships if not bool(m.is_owner)]

    return {
        'team_memberships': memberships,
        'my_team_memberships': my_teams,
        'other_team_memberships': other_teams,
        'notifications': Notification.objects.filter(
            user=request.user, is_read=False
        )[:30],
        'task_layout': layout,
    }
