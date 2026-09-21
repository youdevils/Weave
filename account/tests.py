"""
The log-in and sign-up pages are stubs: real pages at their real URLs that never
create a user, authenticate anyone, or change account state.
"""

from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.test import Client, TestCase
from django.urls import reverse


class AccountStubTests(TestCase):

    def setUp(self):
        self.users = get_user_model().objects

    def test_the_stub_pages_live_at_login_and_signup(self):
        self.assertEqual(reverse("account:login"), "/login/")
        self.assertEqual(reverse("account:signup"), "/signup/")

    def test_the_pages_render_for_anonymous_visitors(self):
        for name, heading in (("account:login", "Log in to FacetFold"), ("account:signup", "Try FacetFold free")):
            response = self.client.get(reverse(name))

            self.assertEqual(response.status_code, 200, name)
            self.assertContains(response, heading)
            self.assertContains(response, "FacetFold")

    def test_the_pages_offer_no_credential_form(self):
        for name in ("account:login", "account:signup"):
            html = self.client.get(reverse(name)).content.decode()

            self.assertNotIn("<form", html, name)
            self.assertNotIn('type="password"', html, name)

    def test_posting_is_not_accepted_and_changes_nothing(self):
        credentials = {"email": "new@example.com", "password": "correct horse battery staple"}

        for name in ("account:login", "account:signup"):
            response = self.client.post(reverse(name), credentials)

            self.assertEqual(response.status_code, 405, name)

        self.assertEqual(self.users.count(), 0)
        self.assertEqual(Session.objects.count(), 0)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_existing_users_are_not_logged_in_or_altered(self):
        user = self.users.create_user(email="member@example.com", password="pw-12345-pw")
        before = (user.email, user.password, user.email_verified, user.is_active)

        self.client.post(reverse("account:login"), {"email": "member@example.com", "password": "pw-12345-pw"})

        user.refresh_from_db()
        self.assertEqual((user.email, user.password, user.email_verified, user.is_active), before)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_visiting_the_pages_does_not_start_a_session(self):
        for name in ("account:login", "account:signup"):
            self.client.get(reverse(name))

        self.assertEqual(Session.objects.count(), 0)

    def test_a_signed_in_user_sees_the_pages_without_being_changed(self):
        user = self.users.create_user(email="member@example.com", password="pw-12345-pw")
        client = Client()
        client.force_login(user)

        response = client.get(reverse("account:login"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Open FacetFold")

    def test_the_pages_are_not_offered_to_search_engines(self):
        for name in ("account:login", "account:signup"):
            self.assertContains(self.client.get(reverse(name)), '<meta name="robots" content="noindex">')

    def test_the_login_url_setting_points_at_the_login_page(self):
        from django.conf import settings

        self.assertEqual(settings.LOGIN_URL, "account:login")
