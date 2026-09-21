import logging

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client, TestCase
from django.urls import reverse

VALID = {"name": "Ada Lovelace", "email": "ada@example.com", "message": "This is a private message."}


class ContactFormTests(TestCase):

    url = property(lambda self: reverse("website:contact"))

    def test_the_form_renders_with_a_csrf_token_and_labelled_fields(self):
        html = self.client.get(self.url).content.decode()

        self.assertIn("csrfmiddlewaretoken", html)
        for field in ("name", "email", "message"):
            self.assertIn(f'for="id_{field}"', html)
            self.assertIn(f'id="id_{field}"', html)
        self.assertIn('type="email"', html)
        self.assertIn(f'action="{self.url}"', html)

    def test_a_valid_submission_redirects_to_a_success_state(self):
        response = self.client.post(self.url, VALID)

        self.assertRedirects(response, f"{self.url}?sent=1", fetch_redirect_response=False)

        page = self.client.get(f"{self.url}?sent=1")
        self.assertContains(page, "Thanks for getting in touch.")
        self.assertNotContains(page, "<form")

    def test_the_success_state_is_not_shown_on_a_plain_visit(self):
        page = self.client.get(self.url)

        self.assertNotContains(page, "Thanks for getting in touch.")
        self.assertContains(page, "<form")

    def test_a_valid_submission_does_nothing_else(self):
        """Stub: nothing is logged, stored, or sent."""

        users_before = get_user_model().objects.count()

        with self.assertNoLogs(level=logging.DEBUG):
            with self.assertNumQueries(0):
                response = self.client.post(self.url, VALID)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(mail.outbox, [])
        self.assertEqual(get_user_model().objects.count(), users_before)

    def test_submitted_content_never_appears_in_the_response_or_the_redirect(self):
        response = self.client.post(self.url, VALID, follow=True)

        for value in VALID.values():
            self.assertNotContains(response, value)
            self.assertNotIn(value, response.redirect_chain[0][0])

    def test_missing_fields_re_render_with_errors_and_keep_the_input(self):
        response = self.client.post(self.url, {"name": "Ada", "email": "", "message": ""})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Please check the highlighted fields")
        self.assertContains(response, 'aria-invalid="true"')
        self.assertContains(response, 'value="Ada"')

    def test_an_invalid_email_is_rejected(self):
        response = self.client.post(self.url, {**VALID, "email": "not-an-email"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="email-error"')

    def test_length_limits_are_enforced(self):
        for field, too_long in (("name", "x" * 101), ("message", "x" * 5001)):
            response = self.client.post(self.url, {**VALID, field: too_long})

            self.assertEqual(response.status_code, 200, field)
            self.assertContains(response, f'id="{field}-error"')

    def test_whitespace_only_fields_are_rejected(self):
        response = self.client.post(self.url, {**VALID, "message": "   \n  "})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="message-error"')

    def test_submitted_markup_is_escaped_when_the_form_is_redisplayed(self):
        payload = "<script>alert(1)</script>"

        response = self.client.post(self.url, {"name": payload, "email": "bad", "message": payload})

        html = response.content.decode()
        self.assertNotIn(payload, html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)

    def test_csrf_is_enforced(self):
        client = Client(enforce_csrf_checks=True)

        self.assertEqual(client.post(self.url, VALID).status_code, 403)

    def test_other_methods_are_not_allowed(self):
        for method in ("put", "delete", "patch"):
            self.assertEqual(getattr(self.client, method)(self.url).status_code, 405, method)
