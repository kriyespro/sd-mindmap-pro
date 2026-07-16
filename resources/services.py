from datetime import date, timedelta
from django.contrib.auth import get_user_model
from django.db.models import Q, Sum
from projects.models import Project, ProjectMember
from resources.models import ResourceAllocation
from timetracking.models import TimeEntry

User = get_user_model()


def get_user_allocations(user, weeks=4):
    today = date.today()
    end = today + timedelta(weeks=weeks)
    return ResourceAllocation.objects.filter(
        user=user, start_date__lte=end, end_date__gte=today
    ).select_related('project')


def get_project_allocations(project):
    return ResourceAllocation.objects.filter(project=project).select_related('user', 'project')


def get_workload_data(owner, weeks=4):
    today = date.today()
    # Collect all users visible to owner (project members across owned projects)
    owned_project_ids = Project.objects.filter(owner=owner).values_list('id', flat=True)
    member_user_ids = set(
        ProjectMember.objects.filter(project_id__in=owned_project_ids).values_list('user_id', flat=True)
    )
    member_user_ids.add(owner.id)
    users = list(User.objects.filter(id__in=member_user_ids).order_by('username'))

    monday = today - timedelta(days=today.weekday())
    week_starts = [monday + timedelta(weeks=i) for i in range(weeks)]
    range_start, range_end = week_starts[0], week_starts[-1] + timedelta(days=6)

    # Fetch once for the whole span, bucket per-week in Python instead of
    # issuing 2 queries per (user, week) pair.
    allocs_by_user = {}
    for a in ResourceAllocation.objects.filter(
        user_id__in=member_user_ids, start_date__lte=range_end, end_date__gte=range_start
    ):
        allocs_by_user.setdefault(a.user_id, []).append(a)

    logged_by_user_week = {}
    entries = (
        TimeEntry.objects.filter(
            user_id__in=member_user_ids,
            started_at__date__gte=range_start,
            started_at__date__lte=range_end,
            status='stopped',
        )
        .values('user_id', 'started_at__date')
        .annotate(total=Sum('duration_seconds'))
    )
    for row in entries:
        entry_week = row['started_at__date'] - timedelta(days=row['started_at__date'].weekday())
        key = (row['user_id'], entry_week)
        logged_by_user_week[key] = logged_by_user_week.get(key, 0) + (row['total'] or 0)

    result = []
    for user in users:
        weeks_data = []
        user_allocs = allocs_by_user.get(user.id, [])
        for ws in week_starts:
            we = ws + timedelta(days=6)
            allocated_hours = 0
            for a in user_allocs:
                if a.start_date > we or a.end_date < ws:
                    continue
                overlap_start = max(a.start_date, ws)
                overlap_end = min(a.end_date, we)
                days = max(0, (overlap_end - overlap_start).days + 1)
                # Exclude weekends from working days
                working_days = sum(1 for d in range(days) if (overlap_start + timedelta(d)).weekday() < 5)
                allocated_hours += float(a.hours_per_day) * working_days

            logged = logged_by_user_week.get((user.id, ws), 0)
            logged_hours = round(logged / 3600, 1)

            capacity = 40  # 8h * 5 days
            pct = min(round((allocated_hours / capacity) * 100), 150) if capacity else 0
            weeks_data.append({
                'week_start': ws,
                'allocated': round(allocated_hours, 1),
                'logged': logged_hours,
                'capacity': capacity,
                'pct': pct,
                'over': pct > 100,
            })

        total_alloc = sum(w['allocated'] for w in weeks_data)
        result.append({'user': user, 'weeks': weeks_data, 'total_alloc': total_alloc})

    return {'users': result, 'week_starts': week_starts}


def get_accessible_projects(user):
    owned = Project.objects.filter(owner=user, is_archived=False)
    member = Project.objects.filter(members__user=user, is_archived=False)
    return (owned | member).distinct().order_by('name')
