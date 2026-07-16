from django.contrib.auth import get_user_model
from django.test import TestCase

from planner.services import assignee_choices, resolve_assignee
from projects.models import Project, ProjectMember
from teams.models import Team, TeamMembership

User = get_user_model()


class AssigneeLogicTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='owner', password='pass1234')
        self.member = User.objects.create_user(username='member', password='pass1234')
        self.outsider = User.objects.create_user(username='outsider', password='pass1234')
        self.team = Team.objects.create(name='Alpha', created_by=self.owner)
        TeamMembership.objects.create(team=self.team, user=self.owner, is_owner=True, is_active=True)
        TeamMembership.objects.create(team=self.team, user=self.member, is_owner=False, is_active=True)
        self.project = Project.objects.create(
            name='Only Project',
            owner=self.owner,
            team=self.team,
        )
        ProjectMember.objects.create(
            project=self.project, user=self.owner, role=ProjectMember.ROLE_OWNER
        )

    def test_personal_choices_only_me(self):
        self.assertEqual(assignee_choices(actor=self.owner, team=None), ['owner'])

    def test_team_choices_active_members(self):
        choices = assignee_choices(actor=self.owner, team=self.team)
        self.assertEqual(choices, ['member', 'owner'])

    def test_project_choices_exclude_team_only_members(self):
        choices = assignee_choices(actor=self.owner, team=self.team, project=self.project)
        self.assertEqual(choices, ['owner'])
        ProjectMember.objects.create(
            project=self.project, user=self.member, role=ProjectMember.ROLE_MEMBER
        )
        choices = assignee_choices(actor=self.owner, team=self.team, project=self.project)
        self.assertEqual(choices, ['member', 'owner'])

    def test_resolve_unassigned(self):
        name, err = resolve_assignee(actor=self.owner, team=self.team, raw='')
        self.assertEqual(name, '')
        self.assertIsNone(err)

    def test_resolve_team_member(self):
        name, err = resolve_assignee(actor=self.owner, team=self.team, raw='MEMBER')
        self.assertEqual(name, 'member')
        self.assertIsNone(err)

    def test_resolve_rejects_outsider_on_team(self):
        name, err = resolve_assignee(actor=self.owner, team=self.team, raw='outsider')
        self.assertEqual(name, '')
        self.assertIsNotNone(err)

    def test_resolve_rejects_team_member_not_on_project(self):
        name, err = resolve_assignee(
            actor=self.owner, team=self.team, raw='member', project=self.project
        )
        self.assertEqual(name, '')
        self.assertIsNotNone(err)

    def test_personal_only_self(self):
        name, err = resolve_assignee(actor=self.owner, team=None, raw='member')
        self.assertEqual(name, '')
        self.assertIsNotNone(err)
        name, err = resolve_assignee(actor=self.owner, team=None, raw='owner')
        self.assertEqual(name, 'owner')
        self.assertIsNone(err)
