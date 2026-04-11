from decimal import Decimal

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Sum
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import TemplateView
from django.utils import timezone

from billing.models import Payment
from users.models import Profile


class BillingView(LoginRequiredMixin, TemplateView):
    template_name = 'pages/billing.jinja'
    login_url = reverse_lazy('users:login')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        uid = self.request.user.id
        mine = Payment.objects.filter(user_id=uid)
        total = mine.aggregate(s=Sum('amount'))['s'] or Decimal('0')
        ctx['my_payment_total'] = total
        ctx['my_payment_total_display'] = f'{total:.2f}'
        ctx['my_payments'] = mine[:20]
        ctx['is_trial'] = False
        ctx['trial_ends'] = None
        ctx['plan_code'] = 'solo'
        ctx['plan_name'] = 'Solo'
        ctx['trial_days_left'] = 0
        ctx['solo_price_inr'] = 199
        ctx['team_price_inr'] = 399
        ctx['team_user_limit'] = Profile.TEAM_USER_LIMIT
        try:
            p = self.request.user.profile
            ctx['is_trial'] = p.trial_active
            ctx['trial_ends'] = p.trial_ends
            ctx['plan_code'] = p.plan
            ctx['plan_name'] = p.get_plan_display()
            if p.trial_active and p.trial_ends:
                delta = (p.trial_ends - timezone.localdate()).days
                ctx['trial_days_left'] = max(delta, 0)
        except Profile.DoesNotExist:
            pass
        return ctx


class PlanChangeView(LoginRequiredMixin, View):
    login_url = reverse_lazy('users:login')

    def post(self, request):
        plan = (request.POST.get('plan') or '').strip()
        if plan not in {Profile.PLAN_SOLO, Profile.PLAN_TEAM}:
            return HttpResponse('Invalid plan', status=400)

        profile, _ = Profile.objects.get_or_create(user=request.user)
        profile.plan = plan
        profile.save(update_fields=['plan'])
        return redirect('billing:overview')
