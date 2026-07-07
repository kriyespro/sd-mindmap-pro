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
    users = User.objects.filter(id__in=member_user_ids).order_by('username')

    week_starts = [today + timedelta(weeks=i) - timedelta(days=today.weekday()) + timedelta(weeks=i - (0 if today.weekday() == 0 else 0)) for i in range(weeks)]
    # Simple: just use current week + next N-1 weeks
    week_starts = []
    monday = today - timedelta(days=today.weekday())
    for i in range(weeks):
        week_starts.append(monday + timedelta(weeks=i))

    result = []
    for user in users:
        weeks_data = []
        for ws in week_starts:
            we = ws + timedelta(days=6)
            allocs = ResourceAllocation.objects.filter(
                user=user,
                start_date__lte=we,
                end_date__gte=ws,
            )
            allocated_hours = 0
            for a in allocs:
                overlap_start = max(a.start_date, ws)
                overlap_end = min(a.end_date, we)
                days = max(0, (overlap_end - overlap_start).days + 1)
                # Exclude weekends from working days
                working_days = sum(1 for d in range(days) if (overlap_start + timedelta(d)).weekday() < 5)
                allocated_hours += float(a.hours_per_day) * working_days

            logged = TimeEntry.objects.filter(
                user=user,
                started_at__date__gte=ws,
                started_at__date__lte=we,
                status='stopped',
            ).aggregate(s=Sum('duration_seconds'))['s'] or 0
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
