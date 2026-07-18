from __future__ import annotations

from typing import Any

from django.db.models import Exists, OuterRef, Q
from django.urls import reverse

from planner.models import Notification
from planner.models import Task
from planner.services import workspace_root_average_percent_by_team
from teams.models import TeamMembership
from users.ui_mode import get_user_ui_mode, normalize_layout


def workspace_chrome(request: Any) -> dict[str, Any]:
    if not getattr(request, 'user', None) or not request.user.is_authenticated:
        return {}
    layout = request.session.get('task_layout', 'mindmap')
    if layout not in ('tree', 'mindmap', 'cmap', 'mini', 'idea', 'kanban'):
        layout = 'mindmap'
    mode = get_user_ui_mode(request.user)
    layout = normalize_layout(mode, layout)
    if request.session.get('task_layout') != layout:
        request.session['task_layout'] = layout
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
    pct_by_team = workspace_root_average_percent_by_team(
        request.user, [m.team_id for m in memberships]
    )
    for m in memberships:
        setattr(m, 'done_pct', pct_by_team.get(m.team_id, 0))

    my_teams = [m for m in memberships if bool(m.is_owner)]
    other_teams = [m for m in memberships if not bool(m.is_owner)]
    active_team_ids = [m.team_id for m in memberships]
    username = (request.user.username or '').strip()
    my_assigned_tasks = (
        Task.objects.filter(
            assignee_username__iexact=username,
            is_archived=False,
            is_completed=False,
        )
        .filter(Q(team__isnull=True) | Q(team_id__in=active_team_ids))
        .select_related('team')
        .order_by('is_completed', 'due_date', '-id')[:20]
    )

    return {
        'team_memberships': memberships,
        'my_team_memberships': my_teams,
        'other_team_memberships': other_teams,
        'my_assigned_tasks': my_assigned_tasks,
        'notifications': Notification.objects.filter(
            user=request.user, is_read=False
        )[:30],
        'task_layout': layout,
        'sidebar_my_tasks_url': reverse('planner:sidebar_my_tasks'),
    }
