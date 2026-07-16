"""CEO-level Mission Control metrics for staff at /admin/."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from billing.models import Payment
from planner.models import Task
from projects.models import Project
from teams.models import Team, TeamInvite, TeamMembership
from users.models import Profile

User = get_user_model()

# Keep in sync with landing / billing display prices (INR).
PLAN_PRICE_INR = {
    Profile.PLAN_SOLO: 99,
    Profile.PLAN_TEAM: 299,
    Profile.PLAN_TEAM_20: 999,
}


def ceo_snapshot() -> dict:
    """One-shot executive snapshot for the Mission Control home."""
    now = timezone.now()
    today = timezone.localdate()
    week_ago = now - timedelta(days=7)
    month_start = today.replace(day=1)
    in_3_days = today + timedelta(days=3)

    users = User.objects.all()
    active_users = users.filter(is_active=True)
    profiles = Profile.objects.select_related('user')

    pay_agg = Payment.objects.aggregate(total=Sum('amount'), n=Count('id'))
    pay_month = Payment.objects.filter(created_at__date__gte=month_start).aggregate(
        total=Sum('amount'), n=Count('id')
    )
    pay_week = Payment.objects.filter(created_at__gte=week_ago).aggregate(
        total=Sum('amount'), n=Count('id')
    )

    plan_counts = {
        row['plan']: row['c']
        for row in profiles.values('plan').annotate(c=Count('id'))
    }
    for key in (Profile.PLAN_SOLO, Profile.PLAN_TEAM, Profile.PLAN_TEAM_20):
        plan_counts.setdefault(key, 0)

    mrr_inr = sum(PLAN_PRICE_INR[p] * plan_counts[p] for p in PLAN_PRICE_INR)
    paid_users = plan_counts[Profile.PLAN_TEAM] + plan_counts[Profile.PLAN_TEAM_20]

    trials_active = profiles.filter(is_trial=True, trial_ends__gte=today).count()
    trials_ending_soon = list(
        profiles.filter(is_trial=True, trial_ends__gte=today, trial_ends__lte=in_3_days)
        .select_related('user')
        .order_by('trial_ends')[:8]
    )
    trials_expired = profiles.filter(is_trial=True).filter(
        Q(trial_ends__lt=today) | Q(trial_ends__isnull=True)
    ).count()

    signups_today = users.filter(date_joined__date=today).count()
    signups_week = users.filter(date_joined__gte=week_ago).count()
    signups_month = users.filter(date_joined__date__gte=month_start).count()

    teams_total = Team.objects.count()
    seats_filled = TeamMembership.objects.filter(is_active=True).count()
    open_invites = TeamInvite.objects.filter(
        is_revoked=False, expires_at__gt=now, use_count__lt=1
    ).count()

    tasks_open = Task.objects.filter(is_completed=False, is_archived=False).count()
    tasks_done = Task.objects.filter(is_completed=True).count()
    projects_active = Project.objects.filter(is_archived=False).count()

    from planner.models import Notification

    activity_week = Notification.objects.filter(created_at__gte=week_ago).count()

    # Teams near seat limit (owner on Team plan with 4+ of 5, or Pro with 16+ of 20)
    attention_seats = _teams_near_capacity()[:6]

    recent_signups = list(
        users.select_related('profile')
        .order_by('-date_joined')[:10]
    )
    recent_payments = list(
        Payment.objects.select_related('user').order_by('-created_at')[:10]
    )

    # Signup sparkline (last 14 days)
    day_counts = {
        row['d']: row['c']
        for row in users.filter(date_joined__date__gte=today - timedelta(days=13))
        .annotate(d=TruncDate('date_joined'))
        .values('d')
        .annotate(c=Count('id'))
    }
    sparkline = []
    for i in range(13, -1, -1):
        d = today - timedelta(days=i)
        sparkline.append({'date': d, 'count': day_counts.get(d, 0)})
    spark_max = max((s['count'] for s in sparkline), default=1) or 1

    return {
        'as_of': now,
        'revenue_total': pay_agg['total'] or Decimal('0'),
        'revenue_month': pay_month['total'] or Decimal('0'),
        'revenue_week': pay_week['total'] or Decimal('0'),
        'payment_count': pay_agg['n'] or 0,
        'payment_count_month': pay_month['n'] or 0,
        'mrr_inr': mrr_inr,
        'plan_counts': plan_counts,
        'paid_users': paid_users,
        'user_count': active_users.count(),
        'user_total': users.count(),
        'staff_count': users.filter(is_staff=True).count(),
        'signups_today': signups_today,
        'signups_week': signups_week,
        'signups_month': signups_month,
        'trials_active': trials_active,
        'trials_expired_flag': trials_expired,
        'trials_ending_soon': trials_ending_soon,
        'teams_total': teams_total,
        'seats_filled': seats_filled,
        'open_invites': open_invites,
        'activity_week': activity_week,
        'tasks_done': tasks_done,
        'tasks_open': tasks_open,
        'projects_active': projects_active,
        'attention_seats': attention_seats,
        'recent_signups': recent_signups,
        'recent_payments': recent_payments,
        'sparkline': sparkline,
        'spark_max': spark_max,
        'plan_price': PLAN_PRICE_INR,
    }


def _teams_near_capacity() -> list[dict]:
    filled_map = {
        row['team_id']: row['c']
        for row in TeamMembership.objects.filter(is_active=True)
        .values('team_id')
        .annotate(c=Count('id'))
    }
    rows = []
    memberships = (
        TeamMembership.objects.filter(is_owner=True, is_active=True)
        .select_related('team', 'user__profile')
    )
    for m in memberships:
        try:
            plan = m.user.profile.plan
        except Profile.DoesNotExist:
            plan = Profile.PLAN_TEAM
        limit = Profile.seat_limit_for_plan(plan)
        if limit <= 1:
            continue
        filled = filled_map.get(m.team_id, 0)
        if filled >= max(limit - 1, 1) and filled >= 2:
            rows.append(
                {
                    'team': m.team,
                    'owner': m.user,
                    'filled': filled,
                    'limit': limit,
                    'plan': plan,
                }
            )
    rows.sort(key=lambda r: r['filled'] / r['limit'], reverse=True)
    return rows


def search_users(*, q: str = '', plan: str = '', limit: int = 40):
    qs = (
        User.objects.select_related('profile')
        .annotate(
            team_count=Count('team_memberships', filter=Q(team_memberships__is_active=True)),
            payment_count=Count('payments'),
        )
        .order_by('-date_joined')
    )
    q = (q or '').strip()
    if q:
        qs = qs.filter(
            Q(username__icontains=q)
            | Q(email__icontains=q)
            | Q(first_name__icontains=q)
            | Q(last_name__icontains=q)
        )
    plan = (plan or '').strip()
    if plan in {Profile.PLAN_SOLO, Profile.PLAN_TEAM, Profile.PLAN_TEAM_20}:
        qs = qs.filter(profile__plan=plan)
    return list(qs[:limit])


def set_user_plan(*, actor, user, plan: str) -> tuple[bool, str]:
    if plan not in PLAN_PRICE_INR:
        return False, 'Invalid plan'
    profile, _ = Profile.objects.get_or_create(user=user)
    old = profile.plan
    profile.plan = plan
    if plan != Profile.PLAN_SOLO:
        profile.is_trial = False
    profile.save(update_fields=['plan', 'is_trial'])
    return True, f'@{user.username}: {old} → {plan} (by {actor.username})'


def end_user_trial(*, actor, user) -> tuple[bool, str]:
    profile, _ = Profile.objects.get_or_create(user=user)
    profile.is_trial = False
    profile.save(update_fields=['is_trial'])
    return True, f'@{user.username} trial ended (by {actor.username})'


def set_user_active(*, actor, user, is_active: bool) -> tuple[bool, str]:
    if user.id == actor.id:
        return False, 'Cannot deactivate yourself'
    if user.is_superuser and not is_active:
        return False, 'Cannot deactivate a superuser from here'
    user.is_active = is_active
    user.save(update_fields=['is_active'])
    state = 'activated' if is_active else 'deactivated'
    return True, f'@{user.username} {state} (by {actor.username})'
