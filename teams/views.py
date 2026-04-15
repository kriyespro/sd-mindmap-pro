from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import View
from django.utils import timezone

from planner.models import Notification
from planner.models import Task
from teams.forms import TeamCreateForm, TeamInviteForm
from teams.models import Team, TeamInvite, TeamMembership
from users.models import Profile

User = get_user_model()


def _clear_team_assignee_labels_for_user(*, team: Team, username: str) -> None:
    target = (username or '').strip().lower()
    if not target:
        return
    for task in Task.objects.filter(team=team).only('id', 'assignee_username'):
        current = (task.assignee_username or '').strip().lower()
        if current != target:
            continue
        task.assignee_username = ''
        task.save(update_fields=['assignee_username'])


def _team_seat_limit(team: Team) -> int:
    owner = (
        TeamMembership.objects.filter(team=team, is_owner=True, is_active=True)
        .select_related('user__profile')
        .first()
    )
    if owner:
        try:
            return Profile.seat_limit_for_plan(owner.user.profile.plan)
        except Profile.DoesNotExist:
            return Profile.TEAM_USER_LIMIT
    if team.created_by:
        try:
            return Profile.seat_limit_for_plan(team.created_by.profile.plan)
        except Profile.DoesNotExist:
            return Profile.TEAM_USER_LIMIT
    return Profile.TEAM_USER_LIMIT


class TeamCreateView(LoginRequiredMixin, View):
    def post(self, request):
        try:
            profile = request.user.profile
        except Profile.DoesNotExist:
            return HttpResponse('Upgrade to Team plan (₹399/mo) to create teams', status=403)
        if not Profile.supports_team_plan(profile.plan):
            return HttpResponse('Upgrade to Team plan (₹399/mo) to create teams', status=403)
        form = TeamCreateForm(request.POST)
        if not form.is_valid():
            return HttpResponse('Invalid team name', status=400)
        team = form.save(commit=False)
        team.created_by = request.user
        team.save()
        TeamMembership.objects.create(team=team, user=request.user, is_owner=True)
        url = reverse('planner:board_team', kwargs={'team_slug': team.slug})
        if request.headers.get('HX-Request'):
            resp = HttpResponse()
            resp['HX-Redirect'] = url
            return resp
        return redirect(url)


class TeamInviteView(LoginRequiredMixin, View):
    """Owner/admin can invite by username (join link bound to that account)."""

    def post(self, request, team_slug):
        team = get_object_or_404(Team, slug=team_slug)
        membership = TeamMembership.objects.filter(team=team, user=request.user, is_active=True).first()
        if not membership or not membership.can_manage_invites:
            return HttpResponse('Only owner/admin can invite', status=403)
        try:
            profile = request.user.profile
        except Profile.DoesNotExist:
            return HttpResponse('Upgrade to Team plan to invite members', status=403)
        if not Profile.supports_team_plan(profile.plan):
            return HttpResponse('Upgrade to Team plan (₹399/mo) to invite members', status=403)
        seat_limit = _team_seat_limit(team)
        if TeamMembership.objects.filter(team=team, is_active=True).count() >= seat_limit:
            return HttpResponse(f'Team member limit reached (max {seat_limit} users)', status=400)

        form = TeamInviteForm(request.POST)
        if not form.is_valid():
            return HttpResponse('Enter a valid username and role', status=400)

        raw_username = (form.cleaned_data.get('username') or '').strip()
        role = form.cleaned_data['role']

        existing_user = User.objects.filter(username__iexact=raw_username).first()
        if not existing_user:
            return HttpResponse('No user with that username', status=400)
        if TeamMembership.objects.filter(team=team, user=existing_user, is_active=True).exists():
            return HttpResponse('That user is already a member', status=400)

        invite = TeamInvite.objects.create(
            team=team,
            invited_by=request.user,
            email='',
            invited_username=existing_user.username,
            role=role,
            expires_at=timezone.now() + timedelta(days=7),
            max_uses=1,
        )
        accept_url = request.build_absolute_uri(
            reverse('teams:accept_invite', kwargs={'token': invite.token})
        )
        Notification.objects.create(
            user=existing_user,
            message=f'{request.user.username} invited you to "{team.name}". Join: {accept_url}',
        )

        url = reverse('billing:overview')
        if request.headers.get('HX-Request'):
            resp = HttpResponse()
            resp['HX-Redirect'] = url
            return resp
        return redirect(url)


class TeamJoinLinkGenerateView(LoginRequiredMixin, View):
    """Owner/admin can generate a reusable team join link."""

    def post(self, request, team_slug):
        team = get_object_or_404(Team, slug=team_slug)
        membership = TeamMembership.objects.filter(team=team, user=request.user, is_active=True).first()
        if not membership or not membership.can_manage_invites:
            return HttpResponse('Only owner/admin can generate links', status=403)
        try:
            profile = request.user.profile
        except Profile.DoesNotExist:
            return HttpResponse('Upgrade to Team plan to generate links', status=403)
        if not Profile.supports_team_plan(profile.plan):
            return HttpResponse('Upgrade to Team plan (₹399/mo) to generate links', status=403)

        role = request.POST.get('role', TeamInvite.ROLE_MEMBER)
        if role not in {TeamInvite.ROLE_ADMIN, TeamInvite.ROLE_MEMBER}:
            return HttpResponse('Invalid role', status=400)

        TeamInvite.objects.filter(
            team=team, invited_by=request.user, email='', invited_username=''
        ).update(is_revoked=True)
        seat_limit = _team_seat_limit(team)
        invite = TeamInvite.objects.create(
            team=team,
            invited_by=request.user,
            email='',
            role=role,
            expires_at=timezone.now() + timedelta(days=7),
            max_uses=max(seat_limit, 1),
        )
        request.session['latest_team_join_token'] = invite.token
        return redirect('billing:overview')


class TeamInviteAcceptView(View):
    """Accept team invite token, with login/signup redirect when needed."""

    def get(self, request, token):
        invite = get_object_or_404(
            TeamInvite.objects.select_related('team'),
            token=token,
        )
        if not invite.is_usable:
            messages.error(request, 'This invite link is invalid, used, revoked, or expired.')
            return redirect('billing:overview')

        if not request.user.is_authenticated:
            login_url = reverse('users:login')
            return redirect(f'{login_url}?next={request.path}')

        if invite.invited_username:
            if request.user.username.lower() != invite.invited_username.lower():
                messages.error(request, 'This invite is for a different user account.')
                return redirect('billing:overview')
        elif invite.email and request.user.email.lower() != invite.email.lower():
            messages.error(request, 'This invite is bound to a different email account.')
            return redirect('billing:overview')

        seat_limit = _team_seat_limit(invite.team)
        if TeamMembership.objects.filter(team=invite.team, is_active=True).count() >= seat_limit:
            messages.error(request, f'Team seat limit reached ({seat_limit}). Ask the owner to upgrade.')
            return redirect('billing:overview')

        membership, created = TeamMembership.objects.get_or_create(
            team=invite.team,
            user=request.user,
            defaults={
                'is_owner': False,
                'is_active': True,
                'role': invite.role,
            },
        )
        if not created and not membership.is_active:
            membership.is_active = True
            membership.role = invite.role
            membership.save(update_fields=['is_active', 'role'])
            invite.use_count += 1
            invite.accepted_at = timezone.now()
            invite.accepted_by = request.user
            invite.save(update_fields=['use_count', 'accepted_at', 'accepted_by'])
            messages.success(request, f'Joined team "{invite.team.name}" successfully.')
        elif not created:
            messages.info(request, 'You are already a member of this team.')
        else:
            invite.use_count += 1
            invite.accepted_at = timezone.now()
            invite.accepted_by = request.user
            invite.save(update_fields=['use_count', 'accepted_at', 'accepted_by'])
            messages.success(request, f'Joined team "{invite.team.name}" successfully.')

        return redirect('planner:board_team', team_slug=invite.team.slug)


class TeamMemberAddView(LoginRequiredMixin, View):
    """Owner can directly add existing user to team."""

    def post(self, request, team_slug):
        team = get_object_or_404(Team, slug=team_slug)
        owner_membership = TeamMembership.objects.filter(
            team=team, user=request.user, is_owner=True, is_active=True
        ).first()
        if not owner_membership:
            return HttpResponse('Only owner can manage team members', status=403)

        seat_limit = _team_seat_limit(team)
        if TeamMembership.objects.filter(team=team, is_active=True).count() >= seat_limit:
            return HttpResponse(f'Team member limit reached (max {seat_limit} users)', status=400)

        username = (request.POST.get('username') or '').strip()
        role = (request.POST.get('role') or TeamMembership.ROLE_MEMBER).strip()
        if not username:
            return HttpResponse('Username is required', status=400)
        if role not in {TeamMembership.ROLE_ADMIN, TeamMembership.ROLE_MEMBER}:
            return HttpResponse('Invalid role', status=400)

        user = User.objects.filter(username__iexact=username).first()
        if not user:
            return HttpResponse('No user with that username', status=400)
        existing = TeamMembership.objects.filter(team=team, user=user).first()
        if existing and existing.is_active:
            return HttpResponse('That user is already in this team', status=400)
        if existing:
            existing.is_active = True
            existing.role = role
            existing.save(update_fields=['is_active', 'role'])
        else:
            TeamMembership.objects.create(
                team=team,
                user=user,
                is_owner=False,
                is_active=True,
                role=role,
            )
        Notification.objects.create(
            user=user,
            message=f'{request.user.username} added you to "{team.name}" team.',
        )
        return redirect('billing:overview')


class TeamMemberRemoveView(LoginRequiredMixin, View):
    """Owner can deactivate member from team without deleting account."""

    def post(self, request, team_slug, membership_id):
        team = get_object_or_404(Team, slug=team_slug)
        owner_membership = TeamMembership.objects.filter(
            team=team, user=request.user, is_owner=True, is_active=True
        ).first()
        if not owner_membership:
            return HttpResponse('Only owner can manage team members', status=403)

        target = get_object_or_404(TeamMembership, pk=membership_id, team=team)
        if target.is_owner:
            return HttpResponse('Owner cannot be removed', status=400)

        removed_username = target.user.username
        removed_user = target.user
        target.is_active = False
        target.save(update_fields=['is_active'])
        # Prevent stale task cards showing deactivated user as assignee in this team.
        _clear_team_assignee_labels_for_user(team=team, username=removed_username)
        Notification.objects.create(
            user=removed_user,
            message=f'{request.user.username} deactivated your access to "{team.name}" team.',
        )
        messages.success(request, f'Deactivated @{removed_username} from team.')
        return redirect('billing:overview')


class TeamMemberStatusView(LoginRequiredMixin, View):
    """Owner can activate/deactivate team members."""

    def post(self, request, team_slug, membership_id):
        team = get_object_or_404(Team, slug=team_slug)
        owner_membership = TeamMembership.objects.filter(
            team=team, user=request.user, is_owner=True, is_active=True
        ).first()
        if not owner_membership:
            return HttpResponse('Only owner can manage team members', status=403)

        target = get_object_or_404(TeamMembership, pk=membership_id, team=team)
        if target.is_owner:
            return HttpResponse('Owner cannot be deactivated', status=400)

        desired = (request.POST.get('is_active') or '').strip().lower()
        if desired not in {'true', 'false'}:
            return HttpResponse('Invalid status', status=400)
        should_be_active = desired == 'true'

        if should_be_active and not target.is_active:
            seat_limit = _team_seat_limit(team)
            active_count = TeamMembership.objects.filter(team=team, is_active=True).count()
            if active_count >= seat_limit:
                return HttpResponse(
                    f'Team member limit reached (max {seat_limit} users)', status=400
                )
        target.is_active = should_be_active
        target.save(update_fields=['is_active'])
        if not should_be_active:
            _clear_team_assignee_labels_for_user(team=team, username=target.user.username)

        verb = 'activated' if should_be_active else 'deactivated'
        Notification.objects.create(
            user=target.user,
            message=f'{request.user.username} {verb} your access to "{team.name}" team.',
        )
        messages.success(request, f'{verb.title()} @{target.user.username}.')
        return redirect('billing:overview')
