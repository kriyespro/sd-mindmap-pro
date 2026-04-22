from decimal import Decimal

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Sum
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import TemplateView
from django.utils import timezone

from billing.models import Payment
from planner.models import Task
from teams.forms import TeamInviteForm, TeamJoinLinkForm
from teams.models import TeamInvite, TeamMembership
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
        ctx['team_20_price_inr'] = 1999
        ctx['team_user_limit'] = Profile.TEAM_USER_LIMIT
        ctx['team_20_user_limit'] = Profile.TEAM_20_USER_LIMIT
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

        owned_membership = (
            TeamMembership.objects.filter(user=self.request.user, is_owner=True, is_active=True)
            .select_related('team')
            .first()
        )
        any_membership = (
            TeamMembership.objects.filter(user=self.request.user, is_active=True)
            .select_related('team')
            .order_by('-is_owner', 'joined_at')
            .first()
        )
        primary_membership = owned_membership or any_membership
        owner_team = primary_membership.team if primary_membership else None
        billing_is_owner = bool(primary_membership and primary_membership.is_owner)
        billing_can_invite = bool(
            primary_membership and primary_membership.can_manage_invites
        )
        owner_team_member_count = 0
        owner_team_invites = []
        owner_team_members = []
        team_join_url = ''
        owner_team_seat_limit = Profile.TEAM_USER_LIMIT
        if owner_team:
            owner_plan = Profile.PLAN_TEAM
            owner_member = (
                TeamMembership.objects.filter(team=owner_team, is_owner=True, is_active=True)
                .select_related('user__profile')
                .first()
            )
            if owner_member:
                try:
                    owner_plan = owner_member.user.profile.plan
                except Profile.DoesNotExist:
                    owner_plan = Profile.PLAN_TEAM
            owner_team_seat_limit = Profile.seat_limit_for_plan(owner_plan)
            owner_team_member_count = TeamMembership.objects.filter(team=owner_team, is_active=True).count()
            owner_team_members = list(
                TeamMembership.objects.filter(team=owner_team)
                .select_related('user')
                .order_by('-is_active', '-is_owner', 'user__email', 'user__username')
            )
            owner_team_invites = list(
                TeamInvite.objects.filter(team=owner_team).select_related('invited_by')[:10]
            )
            active_join_link = (
                TeamInvite.objects.filter(team=owner_team, email='', invited_username='')
                .order_by('-created_at')
                .first()
            )
            if active_join_link and active_join_link.is_usable:
                team_join_url = self.request.build_absolute_uri(
                    reverse('teams:accept_invite', kwargs={'token': active_join_link.token})
                )

        latest_token = self.request.session.get('latest_team_join_token')
        if latest_token:
            latest_invite = TeamInvite.objects.filter(token=latest_token).first()
            if (
                latest_invite
                and latest_invite.is_usable
                and owner_team
                and latest_invite.team_id == owner_team.id
            ):
                team_join_url = self.request.build_absolute_uri(
                    reverse('teams:accept_invite', kwargs={'token': latest_invite.token})
                )
            else:
                self.request.session.pop('latest_team_join_token', None)

        ctx['owner_team'] = owner_team
        ctx['billing_is_owner'] = billing_is_owner
        ctx['billing_can_invite'] = billing_can_invite
        ctx['owner_team_member_count'] = owner_team_member_count
        ctx['owner_team_seat_limit'] = owner_team_seat_limit
        ctx['owner_team_seat_left'] = max(owner_team_seat_limit - owner_team_member_count, 0)
        ctx['owner_team_members'] = owner_team_members
        ctx['owner_team_invites'] = owner_team_invites
        ctx['team_invite_form'] = TeamInviteForm()
        ctx['team_join_link_form'] = TeamJoinLinkForm()
        ctx['team_member_role_choices'] = TeamMembership.ROLE_CHOICES
        ctx['team_join_url'] = team_join_url
        archived_teams = []
        memberships = (
            TeamMembership.objects.filter(user=self.request.user, is_active=True)
            .select_related('team')
            .order_by('team__name')
        )
        for membership in memberships:
            has_active_tasks = Task.objects.filter(
                team=membership.team,
                is_archived=False,
            ).exists()
            if has_active_tasks:
                continue
            has_archived_tasks = Task.objects.filter(
                team=membership.team,
                is_archived=True,
            ).exists()
            if has_archived_tasks:
                archived_teams.append(membership)
        ctx['archived_team_memberships'] = archived_teams
        return ctx


class PlanChangeView(LoginRequiredMixin, View):
    login_url = reverse_lazy('users:login')

    def post(self, request):
        plan = (request.POST.get('plan') or '').strip()
        if plan not in {Profile.PLAN_SOLO, Profile.PLAN_TEAM, Profile.PLAN_TEAM_20}:
            return HttpResponse('Invalid plan', status=400)

        profile, _ = Profile.objects.get_or_create(user=request.user)
        profile.plan = plan
        profile.save(update_fields=['plan'])
        return redirect('billing:overview')
