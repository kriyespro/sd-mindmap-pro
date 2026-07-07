from django.contrib.auth import get_user_model
from django.test import TestCase, TransactionTestCase
from django.urls import reverse

from projects.models import Project
from users.models import Profile
from users.services import get_tutorial_project, is_tutorial_project, seed_tutorial_for_user
from users.ui_mode import chrome_for_mode, normalize_layout

User = get_user_model()


class LandingPageTests(TestCase):
    def test_public_user_sees_landing_page(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Turn goals into execution')

    def test_authenticated_user_redirects_to_board(self):
        user = User.objects.create_user(username='demo', password='pass1234')
        self.client.force_login(user)
        response = self.client.get('/')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/app/')


class UIModeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='modeuser', password='pass1234')
        self.profile, _ = Profile.objects.get_or_create(user=self.user)
        self.profile.ui_mode = Profile.UI_MODE_MINIMAL
        self.profile.save(update_fields=['ui_mode'])
        self.client.force_login(self.user)

    def test_minimal_chrome_hides_extra_layouts(self):
        chrome = chrome_for_mode(Profile.UI_MODE_MINIMAL)
        self.assertEqual(chrome['layouts'], ['tree', 'mindmap'])
        self.assertFalse(chrome['sidebar']['gantt'])

    def test_normalize_layout_falls_back_for_minimal(self):
        self.assertEqual(
            normalize_layout(Profile.UI_MODE_MINIMAL, 'kanban'),
            'tree',
        )

    def test_minimal_user_blocked_from_gantt(self):
        response = self.client.get('/gantt/')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('planner:board_personal'))

    def test_ui_mode_change_from_billing(self):
        response = self.client.post(
            reverse('billing:ui_mode_change'),
            {'ui_mode': Profile.UI_MODE_EXPRESS},
        )
        self.assertEqual(response.status_code, 302)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.ui_mode, Profile.UI_MODE_EXPRESS)

    def test_express_user_can_open_projects(self):
        self.profile.ui_mode = Profile.UI_MODE_EXPRESS
        self.profile.save(update_fields=['ui_mode'])
        response = self.client.get('/projects/')
        self.assertEqual(response.status_code, 200)


class TutorialSeedTests(TransactionTestCase):
    def test_new_user_gets_welcome_tour_project(self):
        user = User.objects.create_user(username='newbie', password='pass1234')
        project = get_tutorial_project(user)
        self.assertIsNotNone(project)
        self.assertTrue(is_tutorial_project(project))
        self.assertEqual(project.name, 'Welcome Tour')
        user.profile.refresh_from_db()
        self.assertTrue(user.profile.tutorial_seeded)

    def test_seed_is_idempotent(self):
        user = User.objects.create_user(username='repeat', password='pass1234')
        first = seed_tutorial_for_user(user)
        second = seed_tutorial_for_user(user)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(Project.objects.filter(owner=user).count(), 1)

    def test_signup_redirects_to_tutorial_board(self):
        response = self.client.post(
            reverse('users:signup'),
            {
                'username': 'signupuser',
                'email': 'signup@example.com',
                'password1': 'ComplexPass123!',
                'password2': 'ComplexPass123!',
            },
        )
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(username='signupuser')
        project = get_tutorial_project(user)
        self.assertIsNotNone(project)
        self.assertIn(project.slug, response.url)
