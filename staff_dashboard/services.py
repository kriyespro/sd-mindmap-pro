"""CEO-level Mission Control metrics for staff at /admin/."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.contrib.auth import get_user_model
from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from billing.models import Payment
from planner.models import Notification, Task
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

PAID_PLANS = {Profile.PLAN_TEAM, Profile.PLAN_TEAM_20}
FILTER_CHOICES = (
    ('', 'All'),
    ('trial_soon', 'Trial ≤3d'),
    ('trial_active', 'On trial'),
    ('unpaid', 'Paid plan · no $'),
    ('dormant', 'Dormant 14d'),
    ('inactive', 'Deactivated'),
)


def ceo_snapshot() -> dict:
    """One-shot executive snapshot for the Mission Control home."""
    now = timezone.now()
    today = timezone.localdate()
    week_ago = now - timedelta(days=7)
    two_weeks_ago = now - timedelta(days=14)
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

    # Trial → paid conversion (paid accounts / paid + active trials)
    conversion_base = paid_users + trials_active
    conversion_pct = round((paid_users / conversion_base) * 100) if conversion_base else 0

    revenue_month = pay_month['total'] or Decimal('0')
    arpu_month = (
        (revenue_month / paid_users).quantize(Decimal('0.01')) if paid_users else Decimal('0')
    )

    signups_today = users.filter(date_joined__date=today).count()
    signups_week = users.filter(date_joined__gte=week_ago).count()
    signups_prev_week = users.filter(
        date_joined__gte=two_weeks_ago, date_joined__lt=week_ago
    ).count()
    signups_wow = signups_week - signups_prev_week
    signups_month = users.filter(date_joined__date__gte=month_start).count()

    teams_total = Team.objects.count()
    seats_filled = TeamMembership.objects.filter(is_active=True).count()
    open_invites = TeamInvite.objects.filter(
        is_revoked=False, expires_at__gt=now, use_count__lt=1
    ).count()

    tasks_open = Task.objects.filter(is_completed=False, is_archived=False).count()
    tasks_done = Task.objects.filter(is_completed=True).count()
    projects_active = Project.objects.filter(is_archived=False).count()
    activity_week = Notification.objects.filter(created_at__gte=week_ago).count()

    attention_seats = _teams_near_capacity()[:6]
    unpaid_paid = _unpaid_paid_plans()[:8]
    dormant_users = _dormant_users()[:8]

    recent_signups = list(
        users.select_related('profile').order_by('-date_joined')[:10]
    )
    recent_payments = list(
        Payment.objects.select_related('user').order_by('-created_at')[:10]
    )

    sparkline, spark_max = _daily_counts(
        users.filter(date_joined__date__gte=today - timedelta(days=13)),
        'date_joined',
        today,
        days=14,
    )
    cash_spark, cash_spark_max = _daily_sums(
        Payment.objects.filter(created_at__date__gte=today - timedelta(days=13)),
        'created_at',
        today,
        days=14,
    )

    return {
        'as_of': now,
        'revenue_total': pay_agg['total'] or Decimal('0'),
        'revenue_month': revenue_month,
        'revenue_week': pay_week['total'] or Decimal('0'),
        'payment_count': pay_agg['n'] or 0,
        'payment_count_month': pay_month['n'] or 0,
        'mrr_inr': mrr_inr,
        'plan_counts': plan_counts,
        'paid_users': paid_users,
        'conversion_pct': conversion_pct,
        'arpu_month': arpu_month,
        'user_count': active_users.count(),
        'user_total': users.count(),
        'staff_count': users.filter(is_staff=True).count(),
        'signups_today': signups_today,
        'signups_week': signups_week,
        'signups_prev_week': signups_prev_week,
        'signups_wow': signups_wow,
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
        'unpaid_paid': unpaid_paid,
        'dormant_users': dormant_users,
        'recent_signups': recent_signups,
        'recent_payments': recent_payments,
        'sparkline': sparkline,
        'spark_max': spark_max,
        'cash_spark': cash_spark,
        'cash_spark_max': cash_spark_max,
        'plan_price': PLAN_PRICE_INR,
    }


def _daily_counts(qs, field: str, today, *, days: int = 14):
    day_counts = {
        row['d']: row['c']
        for row in qs.annotate(d=TruncDate(field))
        .values('d')
        .annotate(c=Count('id'))
    }
    sparkline = []
    for i in range(days - 1, -1, -1):
        d = today - timedelta(days=i)
        sparkline.append({'date': d, 'count': day_counts.get(d, 0)})
    spark_max = max((s['count'] for s in sparkline), default=1) or 1
    return sparkline, spark_max


def _daily_sums(qs, field: str, today, *, days: int = 14):
    day_sums = {
        row['d']: row['s'] or Decimal('0')
        for row in qs.annotate(d=TruncDate(field))
        .values('d')
        .annotate(s=Sum('amount'))
    }
    sparkline = []
    for i in range(days - 1, -1, -1):
        d = today - timedelta(days=i)
        amt = day_sums.get(d, Decimal('0'))
        sparkline.append({'date': d, 'amount': amt, 'count': float(amt)})
    spark_max = max((s['count'] for s in sparkline), default=1) or 1
    return sparkline, spark_max


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


def _unpaid_paid_plans() -> list:
    """Users on Team/Pro with zero recorded payments — revenue leak."""
    return list(
        User.objects.filter(is_active=True, profile__plan__in=PAID_PLANS)
        .annotate(payment_count=Count('payments'))
        .filter(payment_count=0)
        .select_related('profile')
        .order_by('-date_joined')[:20]
    )


def _dormant_users() -> list:
    now = timezone.now()
    cutoff = now - timedelta(days=14)
    joined_floor = now - timedelta(days=3)
    return list(
        User.objects.filter(is_active=True, is_staff=False)
        .filter(
            Q(last_login__lt=cutoff)
            | Q(last_login__isnull=True, date_joined__lt=joined_floor)
        )
        .select_related('profile')
        .order_by('last_login', 'date_joined')[:20]
    )


def search_users(*, q: str = '', plan: str = '', filter_key: str = '', limit: int = 50):
    today = timezone.localdate()
    now = timezone.now()
    in_3_days = today + timedelta(days=3)
    cutoff = now - timedelta(days=14)
    joined_floor = now - timedelta(days=3)

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

    filter_key = (filter_key or '').strip()
    if filter_key == 'trial_soon':
        qs = qs.filter(
            profile__is_trial=True,
            profile__trial_ends__gte=today,
            profile__trial_ends__lte=in_3_days,
        )
    elif filter_key == 'trial_active':
        qs = qs.filter(profile__is_trial=True, profile__trial_ends__gte=today)
    elif filter_key == 'unpaid':
        qs = qs.filter(profile__plan__in=PAID_PLANS, payment_count=0)
    elif filter_key == 'dormant':
        qs = qs.filter(is_active=True, is_staff=False).filter(
            Q(last_login__lt=cutoff)
            | Q(last_login__isnull=True, date_joined__lt=joined_floor)
        )
    elif filter_key == 'inactive':
        qs = qs.filter(is_active=False)

    return list(qs[:limit])


def user_dossier(user) -> dict:
    """Full customer card for Mission Control detail."""
    profile, _ = Profile.objects.get_or_create(user=user)
    memberships = list(
        TeamMembership.objects.filter(user=user, is_active=True)
        .select_related('team')
        .order_by('-is_owner', 'team__name')
    )
    payments = list(Payment.objects.filter(user=user).order_by('-created_at')[:20])
    pay_total = Payment.objects.filter(user=user).aggregate(s=Sum('amount'))['s'] or Decimal('0')
    task_count = Task.objects.filter(
        assignee_username=user.username, is_archived=False
    ).count()
    project_count = Project.objects.filter(owner=user, is_archived=False).count()
    return {
        'target': user,
        'profile': profile,
        'memberships': memberships,
        'payments': payments,
        'pay_total': pay_total,
        'task_count': task_count,
        'project_count': project_count,
        'plan_choices': Profile.PLAN_CHOICES,
        'plan_price': PLAN_PRICE_INR,
        'seat_limit': Profile.seat_limit_for_plan(profile.plan),
    }


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


def extend_user_trial(*, actor, user, days: int = 7) -> tuple[bool, str]:
    days = max(1, min(int(days), 30))
    profile, _ = Profile.objects.get_or_create(user=user)
    today = timezone.localdate()
    base = profile.trial_ends if profile.trial_ends and profile.trial_ends >= today else today
    profile.is_trial = True
    profile.trial_ends = base + timedelta(days=days)
    profile.save(update_fields=['is_trial', 'trial_ends'])
    return True, f'@{user.username} trial → {profile.trial_ends} (+{days}d by {actor.username})'


def set_user_active(*, actor, user, is_active: bool) -> tuple[bool, str]:
    if user.id == actor.id:
        return False, 'Cannot deactivate yourself'
    if user.is_superuser and not is_active:
        return False, 'Cannot deactivate a superuser from here'
    user.is_active = is_active
    user.save(update_fields=['is_active'])
    state = 'activated' if is_active else 'deactivated'
    return True, f'@{user.username} {state} (by {actor.username})'


def grant_after_payment(
    *,
    actor,
    user,
    plan: str,
    amount: str,
    currency: str = 'INR',
    description: str = '',
) -> tuple[bool, str]:
    """Record payment + set plan in one CEO action."""
    if plan not in PLAN_PRICE_INR:
        return False, 'Invalid plan'
    try:
        amt = Decimal(str(amount).strip())
    except (InvalidOperation, ValueError, AttributeError):
        return False, 'Invalid amount'
    if amt <= 0:
        return False, 'Amount must be > 0'
    currency = (currency or 'INR').strip().upper()[:8] or 'INR'
    desc = (description or '').strip()[:255] or f'Plan {plan} via Mission Control'
    Payment.objects.create(
        user=user,
        amount=amt,
        currency=currency,
        description=f'{desc} · by {actor.username}',
    )
    ok, msg = set_user_plan(actor=actor, user=user, plan=plan)
    if not ok:
        return False, msg
    return True, f'Recorded {currency} {amt} + {msg}'
