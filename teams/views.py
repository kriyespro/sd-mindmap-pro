from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import View

from planner.models import Notification
from teams.forms import TeamCreateForm, TeamInviteForm
from teams.models import Team, TeamMembership
from users.models import Profile

User = get_user_model()


class TeamCreateView(LoginRequiredMixin, View):
    def post(self, request):
        try:
            profile = request.user.profile
        except Profile.DoesNotExist:
            return HttpResponse('Upgrade to Team plan (₹399/mo) to create teams', status=403)
        if profile.plan != Profile.PLAN_TEAM:
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
    """Owners can add existing users by username. Sends an in-app notification."""

    def post(self, request, team_slug):
        team = get_object_or_404(Team, slug=team_slug)
        owner = TeamMembership.objects.filter(
            team=team, user=request.user, is_owner=True
        ).exists()
        if not owner:
            return HttpResponse('Only team owners can invite', status=403)
        try:
            profile = request.user.profile
        except Profile.DoesNotExist:
            return HttpResponse('Upgrade to Team plan to invite members', status=403)
        if profile.plan != Profile.PLAN_TEAM:
            return HttpResponse('Upgrade to Team plan (₹399/mo) to invite members', status=403)
        if TeamMembership.objects.filter(team=team).count() >= Profile.TEAM_USER_LIMIT:
            return HttpResponse('Team member limit reached (max 5 users)', status=400)

        form = TeamInviteForm(request.POST)
        if not form.is_valid():
            return HttpResponse('Enter a valid username', status=400)

        uname = form.cleaned_data['username'].strip()
        if not uname:
            return HttpResponse('Username required', status=400)

        try:
            invitee = User.objects.get(username__iexact=uname)
        except User.DoesNotExist:
            return HttpResponse('No user with that username', status=404)

        if invitee.pk == request.user.pk:
            return HttpResponse('You are already on this team', status=400)

        if TeamMembership.objects.filter(team=team, user=invitee).exists():
            return HttpResponse('That user is already a member', status=400)

        TeamMembership.objects.create(team=team, user=invitee, is_owner=False)
        Notification.objects.create(
            user=invitee,
            message=f'{request.user.username} added you to team "{team.name}"',
        )

        url = reverse('planner:board_team', kwargs={'team_slug': team.slug})
        if request.headers.get('HX-Request'):
            resp = HttpResponse()
            resp['HX-Redirect'] = url
            return resp
        return redirect(url)
