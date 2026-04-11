from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models import Count, Sum
from django.shortcuts import redirect
from django.urls import reverse, reverse_lazy
from django.views.generic import TemplateView

from billing.models import Payment
from planner.models import Task
from teams.models import Team
from users.models import Profile

User = get_user_model()


class StaffDashboardView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    """Custom operations home at /admin/ (staff only). Django admin lives at /sd/."""

    template_name = 'pages/staff_dashboard.jinja'
    login_url = reverse_lazy('users:login')

    def get_login_url(self) -> str:
        from urllib.parse import urlencode

        base = str(reverse_lazy('users:login'))
        return f'{base}?{urlencode({"next": self.request.get_full_path()})}'

    def test_func(self) -> bool:
        return self.request.user.is_authenticated and self.request.user.is_staff

    def handle_no_permission(self):
        from django.contrib import messages

        if self.request.user.is_authenticated:
            messages.error(
                self.request,
                'That area is for staff only (is_staff). Ask an admin to grant access.',
            )
            return redirect('planner:board_personal')
        return redirect(self.get_login_url())

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        pay_agg = Payment.objects.aggregate(
            total=Sum('amount'),
            n=Count('id'),
        )
        total = pay_agg['total'] or Decimal('0')
        ctx['payment_total'] = total
        ctx['payment_total_display'] = f'{total:.2f}'
        ctx['payment_count'] = pay_agg['n'] or 0
        ctx['recent_payments'] = (
            Payment.objects.select_related('user').order_by('-created_at')[:12]
        )
        ctx['user_count'] = User.objects.filter(is_active=True).count()
        ctx['trial_count'] = Profile.objects.filter(is_trial=True).count()
        ctx['task_count'] = Task.objects.count()
        ctx['team_count'] = Team.objects.count()
        return ctx
