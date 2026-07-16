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
    projects = list(Project.objects.filter(owner=user, is_archived=False).order_by('-updated_at')[:10])
    project_ids = [p.id for p in projects]
    counts = (
        Task.objects.filter(project_id__in=project_ids)
        .values('project_id')
        .annotate(total=Count('id'), done=Count('id', filter=Q(is_completed=True)))
    )
    counts_by_project = {row['project_id']: row for row in counts}
    result = []
    for p in projects:
        row = counts_by_project.get(p.id, {'total': 0, 'done': 0})
        total, done = row['total'], row['done']
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
    counts = dict(
        Task.objects.filter(author=user, is_archived=False)
        .values_list('status')
        .annotate(count=Count('id'))
        .values_list('status', 'count')
    )
    return [{'status': val, 'label': label, 'count': counts.get(val, 0)} for val, label in T.STATUS_CHOICES]


def get_tasks_by_priority(user) -> list[dict]:
    from planner.models import Task as T
    counts = dict(
        Task.objects.filter(author=user, is_archived=False, is_completed=False)
        .values_list('priority')
        .annotate(count=Count('id'))
        .values_list('priority', 'count')
    )
    return [{'priority': val, 'label': label, 'count': counts.get(val, 0)} for val, label in T.PRIORITY_CHOICES]


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
