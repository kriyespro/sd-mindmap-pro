from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from users.models import Profile

User = get_user_model()


class BillingPlanChangeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='billuser', password='pass1234')
        self.client.force_login(self.user)

    def test_upgrade_to_team_plan_blocked_without_payment(self):
        response = self.client.post(
            reverse('billing:plan_change'),
            {'plan': Profile.PLAN_TEAM},
        )
        self.assertEqual(response.status_code, 403)
        self.user.refresh_from_db()
        self.assertEqual(self.user.profile.plan, Profile.PLAN_SOLO)

    def test_downgrade_to_solo_allowed(self):
        self.user.profile.plan = Profile.PLAN_TEAM
        self.user.profile.save(update_fields=['plan'])
        response = self.client.post(
            reverse('billing:plan_change'),
            {'plan': Profile.PLAN_SOLO},
        )
        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertEqual(self.user.profile.plan, Profile.PLAN_SOLO)

    def test_reject_invalid_plan(self):
        response = self.client.post(
            reverse('billing:plan_change'),
            {'plan': 'enterprise'},
        )
        self.assertEqual(response.status_code, 400)
