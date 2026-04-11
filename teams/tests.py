from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from teams.models import Team, TeamMembership

User = get_user_model()


class TeamInviteViewTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='owner', password='pass1234')
        self.super_admin = User.objects.create_superuser(
            username='admin',
            email='admin@example.com',
            password='pass1234',
        )
        self.invitee = User.objects.create_user(username='teammate', password='pass1234')
        self.team = Team.objects.create(name='Marketing', created_by=self.owner)
        TeamMembership.objects.create(team=self.team, user=self.owner, is_owner=True)
        owner_profile = self.owner.profile
        owner_profile.plan = owner_profile.PLAN_TEAM
        owner_profile.save(update_fields=['plan'])

    def test_superuser_without_membership_cannot_invite(self):
        self.client.force_login(self.super_admin)

        response = self.client.post(
            reverse('teams:invite', kwargs={'team_slug': self.team.slug}),
            {'username': self.invitee.username},
            HTTP_HX_REQUEST='true',
        )

        self.assertEqual(response.status_code, 403)
        self.assertIn('Only team owners can invite', response.content.decode())

    def test_solo_plan_owner_cannot_invite(self):
        owner_profile = self.owner.profile
        owner_profile.plan = owner_profile.PLAN_SOLO
        owner_profile.save(update_fields=['plan'])
        self.client.force_login(self.owner)

        response = self.client.post(
            reverse('teams:invite', kwargs={'team_slug': self.team.slug}),
            {'username': self.invitee.username},
            HTTP_HX_REQUEST='true',
        )

        self.assertEqual(response.status_code, 403)
        self.assertIn('Upgrade to Team plan', response.content.decode())
        self.assertFalse(
            TeamMembership.objects.filter(team=self.team, user=self.invitee).exists()
        )

    def test_team_plan_respects_five_member_limit(self):
        extra_users = [
            User.objects.create_user(username='u2', password='pass1234'),
            User.objects.create_user(username='u3', password='pass1234'),
            User.objects.create_user(username='u4', password='pass1234'),
            User.objects.create_user(username='u5', password='pass1234'),
        ]
        for user in extra_users:
            TeamMembership.objects.create(team=self.team, user=user, is_owner=False)

        self.client.force_login(self.owner)
        overflow_user = User.objects.create_user(username='u6', password='pass1234')
        response = self.client.post(
            reverse('teams:invite', kwargs={'team_slug': self.team.slug}),
            {'username': overflow_user.username},
            HTTP_HX_REQUEST='true',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('Team member limit reached', response.content.decode())
        self.assertFalse(
            TeamMembership.objects.filter(team=self.team, user=overflow_user).exists()
        )


class TeamCreateViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='creator', password='pass1234')
        self.super_admin = User.objects.create_superuser(
            username='root',
            email='root@example.com',
            password='pass1234',
        )

    def test_solo_plan_user_cannot_create_team(self):
        profile = self.user.profile
        profile.plan = profile.PLAN_SOLO
        profile.save(update_fields=['plan'])
        self.client.force_login(self.user)

        response = self.client.post(
            reverse('teams:create'),
            {'name': 'Blocked Team'},
            HTTP_HX_REQUEST='true',
        )

        self.assertEqual(response.status_code, 403)
        self.assertIn('Upgrade to Team plan', response.content.decode())
        self.assertFalse(Team.objects.filter(name='Blocked Team').exists())

    def test_team_plan_user_can_create_team(self):
        profile = self.user.profile
        profile.plan = profile.PLAN_TEAM
        profile.save(update_fields=['plan'])
        self.client.force_login(self.user)

        response = self.client.post(
            reverse('teams:create'),
            {'name': 'Growth Team'},
            HTTP_HX_REQUEST='true',
        )

        self.assertEqual(response.status_code, 200)
        team = Team.objects.get(name='Growth Team')
        self.assertTrue(
            TeamMembership.objects.filter(
                team=team,
                user=self.user,
                is_owner=True,
            ).exists()
        )

    def test_superuser_on_solo_plan_cannot_create_team(self):
        admin_profile = self.super_admin.profile
        admin_profile.plan = admin_profile.PLAN_SOLO
        admin_profile.save(update_fields=['plan'])
        self.client.force_login(self.super_admin)

        response = self.client.post(
            reverse('teams:create'),
            {'name': 'Admin Team'},
            HTTP_HX_REQUEST='true',
        )

        self.assertEqual(response.status_code, 403)
        self.assertIn('Upgrade to Team plan', response.content.decode())
        self.assertFalse(Team.objects.filter(name='Admin Team').exists())
