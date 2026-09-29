from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

VALID = {"name": "Ada Lovelace", "email": "ada@example.com", "message": "This is a private message."}


@patch("account.services.emails.resend.Emails.send")
class ContactFormTests(TestCase):

    url = property(lambda self: reverse("website:contact"))

    def test_the_form_renders_with_a_csrf_token_and_labelled_fields(self, mock_send):
        html = self.client.get(self.url).content.decode()

        self.assertIn("csrfmiddlewaretoken", html)
        for field in ("name", "email", "message"):
            self.assertIn(f'for="id_{field}"', html)
            self.assertIn(f'id="id_{field}"', html)
        self.assertIn('type="email"', html)
        self.assertIn(f'action="{self.url}"', html)

    def test_a_valid_submission_redirects_to_a_success_state(self, mock_send):
        response = self.client.post(self.url, VALID)

        self.assertRedirects(response, f"{self.url}?sent=1", fetch_redirect_response=False)

        page = self.client.get(f"{self.url}?sent=1")
        self.assertContains(page, "Thanks for getting in touch.")
        self.assertNotContains(page, "<form")

    def test_the_success_state_is_not_shown_on_a_plain_visit(self, mock_send):
        page = self.client.get(self.url)

        self.assertNotContains(page, "Thanks for getting in touch.")
        self.assertContains(page, "<form")

    def test_a_valid_submission_sends_an_email_without_other_side_effects(self, mock_send):
        users_before = get_user_model().objects.count()

        with self.assertNumQueries(0):
            response = self.client.post(self.url, VALID)

        self.assertEqual(response.status_code, 302)
        mock_send.assert_called_once()
        self.assertEqual(get_user_model().objects.count(), users_before)

    @override_settings(WEBSITE_CONTACT_FORM_RECIPIENT="support@onyxjar.com")
    def test_the_email_is_sent_to_the_configured_recipient(self, mock_send):
        self.client.post(self.url, VALID)

        payload = mock_send.call_args[0][0]
        self.assertEqual(payload["to"], ["support@onyxjar.com"])

    def test_the_reply_to_is_the_visitors_email(self, mock_send):
        self.client.post(self.url, VALID)

        payload = mock_send.call_args[0][0]
        self.assertEqual(payload["reply_to"], "ada@example.com")

    def test_the_subject_identifies_the_contact_form_and_the_visitors_name(self, mock_send):
        self.client.post(self.url, VALID)

        payload = mock_send.call_args[0][0]
        self.assertIn("contact form", payload["subject"])
        self.assertIn("Ada Lovelace", payload["subject"])

    def test_submitted_content_never_appears_in_the_response_or_the_redirect(self, mock_send):
        response = self.client.post(self.url, VALID, follow=True)

        for value in VALID.values():
            self.assertNotContains(response, value)
            self.assertNotIn(value, response.redirect_chain[0][0])

    def test_missing_fields_re_render_with_errors_and_keep_the_input(self, mock_send):
        response = self.client.post(self.url, {"name": "Ada", "email": "", "message": ""})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Please check the highlighted fields")
        self.assertContains(response, 'aria-invalid="true"')
        self.assertContains(response, 'value="Ada"')
        mock_send.assert_not_called()

    def test_an_invalid_email_is_rejected(self, mock_send):
        response = self.client.post(self.url, {**VALID, "email": "not-an-email"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="email-error"')
        mock_send.assert_not_called()

    def test_length_limits_are_enforced(self, mock_send):
        for field, too_long in (("name", "x" * 101), ("message", "x" * 5001)):
            response = self.client.post(self.url, {**VALID, field: too_long})

            self.assertEqual(response.status_code, 200, field)
            self.assertContains(response, f'id="{field}-error"')
        mock_send.assert_not_called()

    def test_whitespace_only_fields_are_rejected(self, mock_send):
        response = self.client.post(self.url, {**VALID, "message": "   \n  "})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="message-error"')
        mock_send.assert_not_called()

    def test_submitted_markup_is_escaped_when_the_form_is_redisplayed(self, mock_send):
        payload = "<script>alert(1)</script>"

        response = self.client.post(self.url, {"name": payload, "email": "bad", "message": payload})

        html = response.content.decode()
        self.assertNotIn(payload, html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)

    def test_a_delivery_failure_shows_a_generic_error_and_keeps_the_input(self, mock_send):
        mock_send.side_effect = Exception("Resend is down")

        response = self.client.post(self.url, VALID)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Something went wrong sending your message")
        self.assertContains(response, 'value="Ada Lovelace"')
        self.assertNotContains(response, "Resend is down")

    def test_csrf_is_enforced(self, mock_send):
        client = Client(enforce_csrf_checks=True)

        self.assertEqual(client.post(self.url, VALID).status_code, 403)
        mock_send.assert_not_called()

    def test_other_methods_are_not_allowed(self, mock_send):
        for method in ("put", "delete", "patch"):
            self.assertEqual(getattr(self.client, method)(self.url).status_code, 405, method)
