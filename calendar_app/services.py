import calendar
from datetime import date, timedelta

from planner.models import Task
from milestones.models import Milestone
from projects.models import Project


def get_calendar_events(user, year: int, month: int) -> dict[str, list]:
    """Return events grouped by date string YYYY-MM-DD."""
    # Date range: full month + padding
    first = date(year, month, 1)
    last_day = calendar.monthrange(year, month)[1]
    last = date(year, month, last_day)

    # Fetch tasks (due in range)
    project_ids = Project.objects.filter(owner=user).values_list('id', flat=True)
    tasks = Task.objects.filter(
        author=user,
        is_archived=False,
        due_date__gte=first,
        due_date__lte=last,
    ).order_by('due_date')

    # Fetch milestones
    milestones = Milestone.objects.filter(
        project__owner=user,
        due_date__gte=first,
        due_date__lte=last,
    ).select_related('project').order_by('due_date')

    events: dict[str, list] = {}

    for task in tasks:
        key = task.due_date.strftime('%Y-%m-%d')
        events.setdefault(key, []).append({
            'type': 'task',
            'id': task.id,
            'title': task.title_plain,
            'priority': task.priority,
            'status': task.status,
            'is_completed': task.is_completed,
            'color': _priority_color(task.priority),
        })

    for ms in milestones:
        key = ms.due_date.strftime('%Y-%m-%d')
        events.setdefault(key, []).append({
            'type': 'milestone',
            'id': ms.id,
            'title': ms.name,
            'project': ms.project.name,
            'status': ms.status,
            'color': ms.project.color,
        })

    return events


def build_calendar_weeks(year: int, month: int) -> list[list[date | None]]:
    """Return list of weeks, each week is 7 days (None = padding)."""
    cal = calendar.Calendar(firstweekday=0)
    weeks = []
    for week in cal.monthdatescalendar(year, month):
        weeks.append(week)
    return weeks


def _priority_color(priority: str) -> str:
    return {
        'critical': '#ef4444',
        'high': '#f97316',
        'medium': '#6366f1',
        'low': '#94a3b8',
    }.get(priority, '#6366f1')
