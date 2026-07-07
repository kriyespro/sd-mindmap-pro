from datetime import date, timedelta
from typing import Any

from planner.models import Task
from projects.models import Project


def get_gantt_tasks(project: Project) -> list[dict]:
    """Return tasks with dates for Gantt rendering."""
    tasks = (
        Task.objects.filter(project=project, is_archived=False)
        .order_by('position', 'id')
    )
    return [_task_to_gantt_row(t) for t in tasks]


def _task_to_gantt_row(task: Task) -> dict:
    start = task.start_date or task.due_date or date.today()
    end = task.due_date or (start + timedelta(days=1))
    if end < start:
        end = start + timedelta(days=1)
    return {
        'id': task.id,
        'title': task.title_plain,
        'start': start,
        'end': end,
        'progress': 100 if task.is_completed else 0,
        'status': task.status,
        'priority': task.priority,
        'assignee': task.assignee_username,
        'color': _priority_color(task.priority),
        'duration_days': max(1, (end - start).days + 1),
    }


def _priority_color(priority: str) -> str:
    return {
        'critical': '#ef4444',
        'high': '#f97316',
        'medium': '#6366f1',
        'low': '#94a3b8',
    }.get(priority, '#6366f1')


def compute_gantt_layout(tasks: list[dict], view: str = 'weekly') -> dict:
    """Compute pixel positions for Gantt bars."""
    col_width = {'daily': 40, 'weekly': 28, 'monthly': 14, 'quarterly': 6, 'yearly': 2}.get(view, 28)

    if not tasks:
        today = date.today()
        min_date = today
        max_date = today + timedelta(days=30)
        dates = []
        d = min_date
        while d <= max_date:
            dates.append(d)
            d += timedelta(days=1)
        return {
            'tasks': [],
            'dates': dates,
            'min_date': min_date,
            'max_date': max_date,
            'view': view,
            'col_width': col_width,
            'total_width': len(dates) * col_width,
        }

    all_starts = [t['start'] for t in tasks]
    all_ends = [t['end'] for t in tasks]
    min_date = min(all_starts)
    max_date = max(all_ends)

    # Generate date headers
    dates = []
    d = min_date
    while d <= max_date + timedelta(days=7):
        dates.append(d)
        d += timedelta(days=1)

    # Calculate bar positions
    positioned = []
    for task in tasks:
        offset_days = (task['start'] - min_date).days
        width_days = task['duration_days']
        positioned.append({
            **task,
            'left_px': offset_days * col_width,
            'width_px': max(col_width, width_days * col_width),
        })

    return {
        'tasks': positioned,
        'dates': dates,
        'min_date': min_date,
        'max_date': max_date,
        'view': view,
        'col_width': col_width,
        'total_width': len(dates) * col_width,
    }
