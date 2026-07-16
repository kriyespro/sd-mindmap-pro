from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.generic import TemplateView

from staff_dashboard.services import (
    ceo_snapshot,
    end_user_trial,
    search_users,
    set_user_active,
    set_user_plan,
)
from users.models import Profile

User = get_user_model()


def _safe_next(request, fallback_name: str = 'staff_dashboard:users') -> str:
    next_url = (request.POST.get('next') or '').strip()
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return next_url
    return reverse(fallback_name)


class StaffRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    login_url = reverse_lazy('users:login')

    def get_login_url(self) -> str:
        from urllib.parse import urlencode

        base = str(reverse_lazy('users:login'))
        return f'{base}?{urlencode({"next": self.request.get_full_path()})}'

    def test_func(self) -> bool:
        return self.request.user.is_authenticated and self.request.user.is_staff

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            messages.error(
                self.request,
                'That area is for staff only (is_staff). Ask an admin to grant access.',
            )
            return redirect('planner:board_personal')
        return redirect(self.get_login_url())


class StaffDashboardView(StaffRequiredMixin, TemplateView):
    """CEO Mission Control home at /admin/."""

    template_name = 'pages/staff_dashboard.jinja'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        snap = ceo_snapshot()
        ctx.update(snap)
        ctx['payment_total_display'] = f'{snap["revenue_total"]:.2f}'
        ctx['revenue_month_display'] = f'{snap["revenue_month"]:.2f}'
        ctx['revenue_week_display'] = f'{snap["revenue_week"]:.2f}'
        ctx['nav_active'] = 'dashboard'
        return ctx


class StaffUsersView(StaffRequiredMixin, TemplateView):
    """CEO people directory — search, plan, activate."""

    template_name = 'pages/staff_users.jinja'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        q = (self.request.GET.get('q') or '').strip()
        plan = (self.request.GET.get('plan') or '').strip()
        ctx['q'] = q
        ctx['plan_filter'] = plan
        ctx['users_list'] = search_users(q=q, plan=plan)
        ctx['plan_choices'] = Profile.PLAN_CHOICES
        ctx['nav_active'] = 'users'
        return ctx


class StaffUsersPartialView(StaffRequiredMixin, View):
    """HTMX user table rows."""

    def get(self, request):
        q = (request.GET.get('q') or '').strip()
        plan = (request.GET.get('plan') or '').strip()
        return render(
            request,
            'partials/_staff_user_rows.jinja',
            {
                'users_list': search_users(q=q, plan=plan),
                'plan_choices': Profile.PLAN_CHOICES,
            },
        )


class StaffUserPlanView(StaffRequiredMixin, View):
    """Staff can grant/change plans (self-serve upgrades are blocked)."""

    def post(self, request, user_id):
        target = get_object_or_404(User, pk=user_id)
        plan = (request.POST.get('plan') or '').strip()
        ok, msg = set_user_plan(actor=request.user, user=target, plan=plan)
        if not ok:
            messages.error(request, msg)
        else:
            messages.success(request, msg)
        next_url = _safe_next(request)
        return redirect(next_url)


class StaffUserTrialView(StaffRequiredMixin, View):
    def post(self, request, user_id):
        target = get_object_or_404(User, pk=user_id)
        ok, msg = end_user_trial(actor=request.user, user=target)
        if not ok:
            messages.error(request, msg)
        else:
            messages.success(request, msg)
        next_url = _safe_next(request)
        return redirect(next_url)


class StaffUserActiveView(StaffRequiredMixin, View):
    def post(self, request, user_id):
        target = get_object_or_404(User, pk=user_id)
        raw = (request.POST.get('is_active') or '').strip().lower()
        is_active = raw in {'1', 'true', 'yes', 'on'}
        ok, msg = set_user_active(actor=request.user, user=target, is_active=is_active)
        if not ok:
            messages.error(request, msg)
        else:
            messages.success(request, msg)
        next_url = _safe_next(request)
        return redirect(next_url)


class StaffStatsPartialView(StaffRequiredMixin, View):
    """HTMX refresh for KPI strip."""

    def get(self, request):
        snap = ceo_snapshot()
        return render(
            request,
            'partials/_staff_kpi_strip.jinja',
            {
                **snap,
                'payment_total_display': f'{snap["revenue_total"]:.2f}',
                'revenue_month_display': f'{snap["revenue_month"]:.2f}',
                'revenue_week_display': f'{snap["revenue_week"]:.2f}',
            },
        )
