from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.generic import TemplateView

from staff_dashboard.services import (
    FILTER_CHOICES,
    ceo_snapshot,
    end_user_trial,
    extend_user_trial,
    grant_after_payment,
    search_users,
    set_user_active,
    set_user_plan,
    user_dossier,
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


def _money_ctx(snap: dict) -> dict:
    return {
        **snap,
        'payment_total_display': f'{snap["revenue_total"]:.2f}',
        'revenue_month_display': f'{snap["revenue_month"]:.2f}',
        'revenue_week_display': f'{snap["revenue_week"]:.2f}',
        'arpu_month_display': f'{snap["arpu_month"]:.2f}',
    }


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
        ctx.update(_money_ctx(ceo_snapshot()))
        ctx['nav_active'] = 'dashboard'
        return ctx


class StaffUsersView(StaffRequiredMixin, TemplateView):
    """CEO people directory — search, plan, activate."""

    template_name = 'pages/staff_users.jinja'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        q = (self.request.GET.get('q') or '').strip()
        plan = (self.request.GET.get('plan') or '').strip()
        filter_key = (self.request.GET.get('filter') or '').strip()
        ctx['q'] = q
        ctx['plan_filter'] = plan
        ctx['filter_key'] = filter_key
        ctx['filter_choices'] = FILTER_CHOICES
        ctx['users_list'] = search_users(q=q, plan=plan, filter_key=filter_key)
        ctx['plan_choices'] = Profile.PLAN_CHOICES
        ctx['nav_active'] = 'users'
        return ctx


class StaffUsersPartialView(StaffRequiredMixin, View):
    """HTMX user table rows."""

    def get(self, request):
        q = (request.GET.get('q') or '').strip()
        plan = (request.GET.get('plan') or '').strip()
        filter_key = (request.GET.get('filter') or '').strip()
        return render(
            request,
            'partials/_staff_user_rows.jinja',
            {
                'users_list': search_users(q=q, plan=plan, filter_key=filter_key),
                'plan_choices': Profile.PLAN_CHOICES,
            },
        )


class StaffUserDetailView(StaffRequiredMixin, TemplateView):
    """Customer dossier — convert, extend trial, inspect."""

    template_name = 'pages/staff_user_detail.jinja'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        target = get_object_or_404(User, pk=self.kwargs['user_id'])
        ctx.update(user_dossier(target))
        ctx['nav_active'] = 'users'
        return ctx


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
        return redirect(_safe_next(request))


class StaffUserTrialView(StaffRequiredMixin, View):
    def post(self, request, user_id):
        target = get_object_or_404(User, pk=user_id)
        action = (request.POST.get('action') or 'end').strip().lower()
        if action == 'extend':
            try:
                days = int(request.POST.get('days') or 7)
            except (TypeError, ValueError):
                days = 7
            ok, msg = extend_user_trial(actor=request.user, user=target, days=days)
        else:
            ok, msg = end_user_trial(actor=request.user, user=target)
        if not ok:
            messages.error(request, msg)
        else:
            messages.success(request, msg)
        return redirect(_safe_next(request))


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
        return redirect(_safe_next(request))


class StaffUserConvertView(StaffRequiredMixin, View):
    """One-shot: record payment + grant plan."""

    def post(self, request, user_id):
        target = get_object_or_404(User, pk=user_id)
        ok, msg = grant_after_payment(
            actor=request.user,
            user=target,
            plan=(request.POST.get('plan') or '').strip(),
            amount=(request.POST.get('amount') or '').strip(),
            currency=(request.POST.get('currency') or 'INR').strip(),
            description=(request.POST.get('description') or '').strip(),
        )
        if not ok:
            messages.error(request, msg)
        else:
            messages.success(request, msg)
        detail = reverse('staff_dashboard:user_detail', kwargs={'user_id': user_id})
        next_url = (request.POST.get('next') or '').strip()
        if next_url and url_has_allowed_host_and_scheme(
            next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return redirect(next_url)
        return redirect(detail)


class StaffStatsPartialView(StaffRequiredMixin, View):
    """HTMX refresh for KPI strip."""

    def get(self, request):
        return render(
            request,
            'partials/_staff_kpi_strip.jinja',
            _money_ctx(ceo_snapshot()),
        )
