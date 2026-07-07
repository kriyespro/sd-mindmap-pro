from datetime import date, timedelta

from django.db.models import Count, Q, Sum
from django.utils import timezone

from planner.models import Task
from projects.models import Project
from milestones.models import Milestone
from timetracking.models import TimeEntry


def get_dashboard_stats(user) -> dict:
    today = date.today()
    projects = Project.objects.filter(owner=user, is_archived=False)
    project_ids = projects.values_list('id', flat=True)

    tasks = Task.objects.filter(author=user, is_archived=False)

    return {
        'active_projects': projects.filter(status=Project.STATUS_ACTIVE).count(),
        'total_projects': projects.count(),
        'tasks_due_today': tasks.filter(due_date=today, is_completed=False).count(),
        'overdue_tasks': tasks.filter(due_date__lt=today, is_completed=False).count(),
        'completed_tasks_today': tasks.filter(due_date=today, is_completed=True).count(),
        'total_open_tasks': tasks.filter(is_completed=False).count(),
        'milestones_upcoming': Milestone.objects.filter(
            project__owner=user,
            due_date__gte=today,
            due_date__lte=today + timedelta(days=14),
            status__in=[Milestone.STATUS_PENDING, Milestone.STATUS_IN_PROGRESS],
        ).count(),
        'hours_this_week': _week_hours(user, today),
    }


def get_project_progress(user) -> list[dict]:
    projects = Project.objects.filter(owner=user, is_archived=False).order_by('-updated_at')[:10]
    result = []
    for p in projects:
        total = Task.objects.filter(project=p).count()
        done = Task.objects.filter(project=p, is_completed=True).count()
        pct = int(done / total * 100) if total else 0
        result.append({
            'project': p,
            'total_tasks': total,
            'done_tasks': done,
            'progress': pct,
        })
    return result


def get_tasks_by_status(user) -> list[dict]:
    from planner.models import Task as T
    statuses = T.STATUS_CHOICES
    result = []
    for val, label in statuses:
        count = Task.objects.filter(author=user, status=val, is_archived=False).count()
        result.append({'status': val, 'label': label, 'count': count})
    return result


def get_tasks_by_priority(user) -> list[dict]:
    from planner.models import Task as T
    result = []
    for val, label in T.PRIORITY_CHOICES:
        count = Task.objects.filter(author=user, priority=val, is_archived=False, is_completed=False).count()
        result.append({'priority': val, 'label': label, 'count': count})
    return result


def get_overdue_tasks(user, limit=10):
    today = date.today()
    return Task.objects.filter(
        author=user, due_date__lt=today, is_completed=False, is_archived=False
    ).order_by('due_date').select_related('project')[:limit]


def get_upcoming_milestones(user, days=30):
    today = date.today()
    return Milestone.objects.filter(
        project__owner=user,
        due_date__gte=today,
        due_date__lte=today + timedelta(days=days),
    ).select_related('project').order_by('due_date')[:10]


def _week_hours(user, ref_date: date) -> float:
    monday = ref_date - timedelta(days=ref_date.weekday())
    sunday = monday + timedelta(days=6)
    total_sec = TimeEntry.objects.filter(
        user=user,
        status=TimeEntry.STATUS_STOPPED,
        started_at__date__gte=monday,
        started_at__date__lte=sunday,
    ).aggregate(s=Sum('duration_seconds'))['s'] or 0
    return round(total_sec / 3600, 1)
