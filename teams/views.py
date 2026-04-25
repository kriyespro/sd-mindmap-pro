from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
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


def _add_or_invite_member(
    *,
    request,
    team: Team,
    actor,
    username: str,
    email: str,
    full_name: str,
    role: str,
) -> tuple[bool, str]:
    clean_username = (username or '').strip()
    clean_email = (email or '').strip().lower()
    clean_name = (full_name or '').strip()

    if role not in {TeamMembership.ROLE_ADMIN, TeamMembership.ROLE_MEMBER}:
        return (False, 'Invalid role')
    if not clean_username and not clean_email:
        return (False, 'Enter username, or provide email + name for invite')

    target_user = None
    if clean_username:
        target_user = User.objects.filter(username__iexact=clean_username).first()
    if target_user is None and clean_email:
        target_user = User.objects.filter(email__iexact=clean_email).first()

    if target_user:
        existing = TeamMembership.objects.filter(team=team, user=target_user).first()
        if existing and existing.is_active:
            return (False, 'That user is already in this team')
        if existing:
            existing.is_active = True
            existing.role = role
            existing.save(update_fields=['is_active', 'role'])
        else:
            TeamMembership.objects.create(
                team=team,
                user=target_user,
                is_owner=False,
                is_active=True,
                role=role,
            )
        Notification.objects.create(
            user=target_user,
            message=f'{actor.username} added you to "{team.name}" team.',
        )
        return (True, f'Added @{target_user.username} to {team.name}.')

    if not clean_email:
        return (False, 'No user with that username. Add email + name to send invite.')
    try:
        validate_email(clean_email)
    except ValidationError:
        return (False, 'Enter a valid email address')
    if not clean_name:
        return (False, 'Enter full name for new member invite')

    seat_limit = _team_seat_limit(team)
    usable_invite = TeamInvite.objects.filter(
        team=team,
        email__iexact=clean_email,
        is_revoked=False,
        use_count__lt=1,
        expires_at__gt=timezone.now(),
    ).first()
    if usable_invite:
        return (False, 'Active invite already exists for this email')

    invite = TeamInvite.objects.create(
        team=team,
        invited_by=actor,
        email=clean_email,
        invited_username='',
        role=role,
        expires_at=timezone.now() + timedelta(days=7),
        max_uses=min(max(seat_limit, 1), 1),
    )
    accept_url = request.build_absolute_uri(
        reverse('teams:accept_invite', kwargs={'token': invite.token})
    )
    Notification.objects.create(
        user=actor,
        message=f'Invite created for {clean_name} ({clean_email}) in "{team.name}". Share: {accept_url}',
    )
    messages.info(
        request,
        f'No account found. Invite created for {clean_name} ({clean_email}). Share this join link: {accept_url}',
    )
    return (True, 'Invite created for new member email.')


class TeamCreateView(LoginRequiredMixin, View):
    def post(self, request):
        try:
            profile = request.user.profile
        except Profile.DoesNotExist:
            return HttpResponse(
                'You are on Solo plan. Upgrade to Team plan (₹399/mo) to create teams.',
                status=403,
            )
        if not Profile.supports_team_plan(profile.plan):
            return HttpResponse(
                'You are on Solo plan. Upgrade to Team plan (₹399/mo) to create teams.',
                status=403,
            )
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
        is_hx = bool(request.headers.get('HX-Request'))

        def _error(message: str, *, status: int = 400):
            return HttpResponse(message, status=status)

        next_url = (request.POST.get('next') or '').strip() or request.META.get('HTTP_REFERER') or reverse('billing:overview')
        team = get_object_or_404(Team, slug=team_slug)
        membership = TeamMembership.objects.filter(
            team=team, user=request.user, is_active=True
        ).first()
        if not membership or not membership.can_manage_invites:
            return _error('Only owner/admin can manage team members', status=403)

        seat_limit = _team_seat_limit(team)
        if TeamMembership.objects.filter(team=team, is_active=True).count() >= seat_limit:
            return _error(f'Team member limit reached (max {seat_limit} users)')

        username = (request.POST.get('username') or '').strip()
        email = (request.POST.get('email') or '').strip()
        full_name = (request.POST.get('full_name') or '').strip()
        role = (request.POST.get('role') or TeamMembership.ROLE_MEMBER).strip()
        ok, msg = _add_or_invite_member(
            request=request,
            team=team,
            actor=request.user,
            username=username,
            email=email,
            full_name=full_name,
            role=role,
        )
        if not ok:
            return _error(msg)
        messages.success(request, msg)
        if is_hx:
            resp = HttpResponse('')
            resp['HX-Redirect'] = next_url
            return resp
        return redirect(next_url)


class TeamMemberAddAnyTeamView(LoginRequiredMixin, View):
    """Owner can add user to any owned team from billing page."""

    def post(self, request):
        next_url = (request.POST.get('next') or '').strip() or request.META.get('HTTP_REFERER') or reverse('billing:overview')

        def _fail(message: str):
            messages.error(request, message)
            return redirect(next_url)

        team_slug = (request.POST.get('team_slug') or '').strip()
        if not team_slug:
            return _fail('Select a team first')
        team = Team.objects.filter(slug=team_slug).first()
        if not team:
            return _fail('Team not found')
        owner_membership = TeamMembership.objects.filter(
            team=team, user=request.user, is_owner=True, is_active=True
        ).first()
        if not owner_membership:
            return _fail('Only owner can manage team members')

        username = (request.POST.get('username') or '').strip()
        email = (request.POST.get('email') or '').strip()
        full_name = (request.POST.get('full_name') or '').strip()
        role = (request.POST.get('role') or TeamMembership.ROLE_MEMBER).strip()
        seat_limit = _team_seat_limit(team)
        if TeamMembership.objects.filter(team=team, is_active=True).count() >= seat_limit:
            return _fail(f'Team member limit reached (max {seat_limit} users)')
        ok, msg = _add_or_invite_member(
            request=request,
            team=team,
            actor=request.user,
            username=username,
            email=email,
            full_name=full_name,
            role=role,
        )
        if not ok:
            return _fail(msg)
        messages.success(request, msg)
        return redirect(next_url)


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


class TeamSidebarSettingsView(LoginRequiredMixin, View):
    """Set team color and pin status for the current user in sidebar."""

    def post(self, request, team_slug):
        team = get_object_or_404(Team, slug=team_slug)
        membership = TeamMembership.objects.filter(
            team=team, user=request.user, is_active=True
        ).first()
        if not membership:
            return HttpResponse('Only team members can update sidebar settings', status=403)

        color = (request.POST.get('sidebar_color') or '').strip()
        action = (request.POST.get('pin_action') or '').strip().lower()

        if color and color in {choice[0] for choice in Team.COLOR_CHOICES}:
            team.sidebar_color = color
            team.save(update_fields=['sidebar_color'])

        if action == 'pin':
            if not membership.is_pinned:
                pinned_count = TeamMembership.objects.filter(
                    user=request.user, is_active=True, is_pinned=True
                ).count()
                if pinned_count >= 3:
                    messages.error(request, 'You can pin maximum 3 teams.')
                    return redirect(request.META.get('HTTP_REFERER') or 'billing:overview')
                membership.is_pinned = True
                membership.pinned_at = timezone.now()
                membership.save(update_fields=['is_pinned', 'pinned_at'])
        elif action == 'unpin' and membership.is_pinned:
            membership.is_pinned = False
            membership.pinned_at = None
            membership.save(update_fields=['is_pinned', 'pinned_at'])

        return redirect(request.META.get('HTTP_REFERER') or 'billing:overview')
