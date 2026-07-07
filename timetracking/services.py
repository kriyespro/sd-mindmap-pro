from datetime import date, timedelta

from django.db.models import Sum
from django.utils import timezone

from timetracking.models import TimeEntry


def get_running_timer(user) -> TimeEntry | None:
    return TimeEntry.objects.filter(user=user, status=TimeEntry.STATUS_RUNNING).first()


def start_timer(user, task=None, project=None, description='') -> TimeEntry:
    # Stop any running timer first
    running = get_running_timer(user)
    if running:
        running.stop()
    entry = TimeEntry.objects.create(
        user=user,
        task=task,
        project=project,
        description=description,
        status=TimeEntry.STATUS_RUNNING,
        started_at=timezone.now(),
    )
    return entry


def stop_timer(user) -> TimeEntry | None:
    running = get_running_timer(user)
    if running:
        running.stop()
    return running


def get_daily_seconds(user, d: date) -> int:
    return TimeEntry.objects.filter(
        user=user, status=TimeEntry.STATUS_STOPPED,
        started_at__date=d,
    ).aggregate(total=Sum('duration_seconds'))['total'] or 0


def get_weekly_seconds(user, ref_date: date) -> int:
    monday = ref_date - timedelta(days=ref_date.weekday())
    sunday = monday + timedelta(days=6)
    return TimeEntry.objects.filter(
        user=user, status=TimeEntry.STATUS_STOPPED,
        started_at__date__gte=monday,
        started_at__date__lte=sunday,
    ).aggregate(total=Sum('duration_seconds'))['total'] or 0


def get_recent_entries(user, limit=50):
    return TimeEntry.objects.filter(user=user, status=TimeEntry.STATUS_STOPPED).select_related('task', 'project')[:limit]


def format_seconds(seconds: int) -> str:
    h = seconds // 3600
    m = (seconds % 3600) // 60
    return f'{h}h {m}m'
