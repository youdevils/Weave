from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.contrib.messages import get_messages
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from account.tokens import email_verification_token
from workspace.models import Workspace, WorkspaceMember


@patch("account.services.emails.resend.Emails.send")
class SignupTests(TestCase):

    def setUp(self):
        self.users = get_user_model().objects

    def valid_data(self, **overrides):
        data = {
            "email": "new@example.com",
            "password1": "a-very-strong-pw-93!",
            "password2": "a-very-strong-pw-93!",
        }
        data.update(overrides)
        return data

    def test_valid_signup_creates_an_unverified_user(self, mock_send):
        response = self.client.post(reverse("account:signup"), self.valid_data())

        self.assertRedirects(response, reverse("workspace:index"))
        user = self.users.get(email="new@example.com")
        self.assertFalse(user.email_verified)

    def test_signup_creates_a_workspace_and_owner_membership(self, mock_send):
        self.client.post(reverse("account:signup"), self.valid_data())

        user = self.users.get(email="new@example.com")
        membership = WorkspaceMember.objects.get(user=user)
        self.assertEqual(membership.role, WorkspaceMember.Role.OWNER)
        self.assertEqual(Workspace.objects.count(), 1)

    def test_signup_logs_the_user_in(self, mock_send):
        self.client.post(reverse("account:signup"), self.valid_data())

        self.assertIn("_auth_user_id", self.client.session)

    def test_signup_sends_a_verification_email(self, mock_send):
        self.client.post(reverse("account:signup"), self.valid_data())

        mock_send.assert_called_once()
        params = mock_send.call_args[0][0]
        self.assertEqual(params["to"], ["new@example.com"])

    def test_exactly_one_message_is_queued_for_the_redirect(self, mock_send):
        # The unverified-email notice is workspace:index's job alone, not
        # signup's — otherwise it would be flashed twice: once here, once
        # when the redirect lands on workspace:index.
        response = self.client.post(reverse("account:signup"), self.valid_data(), follow=True)

        stored_messages = list(get_messages(response.wsgi_request))
        self.assertEqual(len(stored_messages), 1)
        self.assertIn("Resend verification email", response.content.decode())

    def test_duplicate_email_is_rejected(self, mock_send):
        self.users.create_user(email="taken@example.com", password="whatever-pw-1")

        response = self.client.post(reverse("account:signup"), self.valid_data(email="taken@example.com"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.users.count(), 1)

    def test_duplicate_email_is_rejected_case_insensitively(self, mock_send):
        self.users.create_user(email="taken@example.com", password="whatever-pw-1")

        response = self.client.post(reverse("account:signup"), self.valid_data(email="TAKEN@example.com"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.users.count(), 1)

    def test_weak_password_is_rejected(self, mock_send):
        response = self.client.post(
            reverse("account:signup"),
            self.valid_data(password1="password", password2="password"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.users.count(), 0)

    def test_mismatched_passwords_are_rejected(self, mock_send):
        response = self.client.post(
            reverse("account:signup"),
            self.valid_data(password2="something-else-99"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.users.count(), 0)

    def test_resend_failure_does_not_block_signup(self, mock_send):
        mock_send.side_effect = Exception("boom")

        response = self.client.post(reverse("account:signup"), self.valid_data())

        self.assertRedirects(response, reverse("workspace:index"))
        self.assertEqual(self.users.count(), 1)
        self.assertIn("_auth_user_id", self.client.session)

    def test_an_authenticated_user_visiting_signup_is_redirected(self, mock_send):
        user = self.users.create_user(email="member@example.com", password="pw-12345-pw")
        self.client.force_login(user)

        response = self.client.get(reverse("account:signup"))

        self.assertRedirects(response, reverse("workspace:index"))


class EmailVerificationTests(TestCase):

    def setUp(self):
        self.users = get_user_model().objects
        self.user = self.users.create_user(email="member@example.com", password="pw-12345-pw")

    def link_for(self, user):
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = email_verification_token.make_token(user)
        return reverse("account:verify_email", kwargs={"uidb64": uid, "token": token})

    def test_a_valid_link_verifies_the_email_and_redirects_to_the_dashboard(self):
        self.client.force_login(self.user)

        response = self.client.get(self.link_for(self.user))

        self.assertRedirects(response, reverse("workspace:index"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.email_verified)

    def test_verifying_does_not_auto_login(self):
        response = self.client.get(self.link_for(self.user))

        self.user.refresh_from_db()
        self.assertTrue(self.user.email_verified)
        self.assertNotIn("_auth_user_id", self.client.session)
        # Anonymous, so the workspace:index redirect itself bounces to login.
        self.assertRedirects(response, reverse("workspace:index"), target_status_code=302)

    def test_an_invalid_token_is_rejected(self):
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        url = reverse("account:verify_email", kwargs={"uidb64": uid, "token": "bogus-token"})

        response = self.client.get(url)

        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertFalse(self.user.email_verified)

    def test_an_expired_token_is_rejected(self):
        link = self.link_for(self.user)

        with override_settings(PASSWORD_RESET_TIMEOUT=-1):
            self.client.get(link)

        self.user.refresh_from_db()
        self.assertFalse(self.user.email_verified)

    def test_a_used_token_cannot_be_replayed(self):
        link = self.link_for(self.user)

        self.client.get(link)
        self.user.refresh_from_db()
        self.assertTrue(self.user.email_verified)

        # The token's hash no longer matches once email_verified flipped, so
        # replaying the exact same link should be rejected cleanly.
        response = self.client.get(link)

        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertTrue(self.user.email_verified)

    def test_an_unknown_uid_is_rejected(self):
        url = reverse("account:verify_email", kwargs={"uidb64": "not-a-real-uid", "token": "whatever"})

        response = self.client.get(url)

        self.assertEqual(response.status_code, 302)


@patch("account.services.emails.resend.Emails.send")
class ResendVerificationTests(TestCase):

    def setUp(self):
        self.user = get_user_model().objects.create_user(email="member@example.com", password="pw-12345-pw")

    def test_resend_requires_login(self, mock_send):
        response = self.client.post(reverse("account:resend_verification"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response["Location"])
        mock_send.assert_not_called()

    def test_resend_requires_post(self, mock_send):
        self.client.force_login(self.user)

        response = self.client.get(reverse("account:resend_verification"))

        self.assertEqual(response.status_code, 405)

    def test_resend_sends_another_email_when_unverified(self, mock_send):
        self.client.force_login(self.user)

        response = self.client.post(reverse("account:resend_verification"))

        self.assertRedirects(response, reverse("workspace:index"))
        mock_send.assert_called_once()

    def test_resend_is_a_no_op_when_already_verified(self, mock_send):
        self.user.email_verified = True
        self.user.save(update_fields=["email_verified"])
        self.client.force_login(self.user)

        self.client.post(reverse("account:resend_verification"))

        mock_send.assert_not_called()


class LoginTests(TestCase):

    def setUp(self):
        self.users = get_user_model().objects
        self.user = self.users.create_user(email="member@example.com", password="correct-horse-1")

    def test_valid_login_redirects_to_the_dashboard(self):
        response = self.client.post(
            reverse("account:login"),
            {"username": "member@example.com", "password": "correct-horse-1"},
        )

        self.assertRedirects(response, reverse("workspace:index"))
        self.assertIn("_auth_user_id", self.client.session)

    def test_invalid_credentials_show_a_generic_error(self):
        response = self.client.post(
            reverse("account:login"),
            {"username": "member@example.com", "password": "wrong-password"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Please enter a correct email address and password.")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_next_parameter_is_honoured(self):
        next_url = reverse("website:contact")

        response = self.client.post(
            reverse("account:login"),
            {"username": "member@example.com", "password": "correct-horse-1", "next": next_url},
        )

        self.assertRedirects(response, next_url)

    def test_unsafe_next_parameter_is_ignored(self):
        response = self.client.post(
            reverse("account:login"),
            {
                "username": "member@example.com",
                "password": "correct-horse-1",
                "next": "https://evil.example/",
            },
        )

        self.assertRedirects(response, reverse("workspace:index"))

    def test_an_authenticated_user_visiting_login_is_redirected(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("account:login"))

        self.assertRedirects(response, reverse("workspace:index"))


class LogoutTests(TestCase):

    def setUp(self):
        self.user = get_user_model().objects.create_user(email="member@example.com", password="pw-12345-pw")

    def test_logout_requires_post(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("account:logout"))

        self.assertEqual(response.status_code, 405)
        self.assertIn("_auth_user_id", self.client.session)

    def test_logout_via_post_ends_the_session_and_redirects_home(self):
        self.client.force_login(self.user)

        response = self.client.post(reverse("account:logout"))

        self.assertRedirects(response, "/")
        self.assertNotIn("_auth_user_id", self.client.session)


@patch("account.services.emails.resend.Emails.send")
class PasswordResetRequestTests(TestCase):

    def setUp(self):
        self.user = get_user_model().objects.create_user(email="member@example.com", password="pw-12345-pw")

    def test_a_known_email_sends_a_reset_email_and_shows_the_generic_response(self, mock_send):
        response = self.client.post(reverse("account:password_reset"), {"email": "member@example.com"})

        self.assertRedirects(response, f"{reverse('account:password_reset')}?sent=1")
        mock_send.assert_called_once()

    def test_an_unknown_email_gives_the_identical_generic_response(self, mock_send):
        response = self.client.post(reverse("account:password_reset"), {"email": "nobody@example.com"})

        self.assertRedirects(response, f"{reverse('account:password_reset')}?sent=1")
        mock_send.assert_not_called()


class PasswordResetConfirmTests(TestCase):

    def setUp(self):
        self.user = get_user_model().objects.create_user(email="member@example.com", password="old-pw-12345")

    def link_for(self, user):
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        return reverse("account:password_reset_confirm", kwargs={"uidb64": uid, "token": token})

    def test_a_valid_link_shows_the_set_password_form(self):
        response = self.client.get(self.link_for(self.user), follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["validlink"])

    def test_submitting_a_new_password_logs_in_and_redirects(self):
        response_get = self.client.get(self.link_for(self.user), follow=True)
        set_password_url = response_get.redirect_chain[-1][0]

        response = self.client.post(
            set_password_url,
            {"new_password1": "brand-new-pw-42!", "new_password2": "brand-new-pw-42!"},
        )

        self.assertRedirects(response, reverse("workspace:index"))
        self.assertIn("_auth_user_id", self.client.session)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("brand-new-pw-42!"))

    def test_the_new_password_must_pass_validators(self):
        response_get = self.client.get(self.link_for(self.user), follow=True)
        set_password_url = response_get.redirect_chain[-1][0]

        response = self.client.post(
            set_password_url,
            {"new_password1": "password", "new_password2": "password"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("old-pw-12345"))

    def test_an_invalid_token_shows_the_invalid_state(self):
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        url = reverse("account:password_reset_confirm", kwargs={"uidb64": uid, "token": "bogus-token"})

        response = self.client.get(url)

        self.assertFalse(response.context["validlink"])

    def test_an_expired_token_shows_the_invalid_state(self):
        link = self.link_for(self.user)

        with override_settings(PASSWORD_RESET_TIMEOUT=-1):
            response = self.client.get(link)

        self.assertFalse(response.context["validlink"])
