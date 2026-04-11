from django.contrib.auth import get_user_model
from django.test import TestCase

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
