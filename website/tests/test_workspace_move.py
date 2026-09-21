"""
The application moved from `/` to `/workspace/` so the root can be the public
site. These tests pin the places that used to assume the old root.
"""

import re
from pathlib import Path

from django.test import TestCase
from django.urls import reverse

from account.models import CustomUser
from model.models.model import Model
from workspace.models import Workspace, WorkspaceMember

WORKSPACE_APP = Path(__file__).resolve().parents[2] / "workspace"


class WorkspaceUnderItsNewPrefixTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = CustomUser.objects.create_user(email="owner@example.com", password="pw")
        cls.workspace = Workspace.objects.create(name="Mine")
        WorkspaceMember.objects.create(workspace=cls.workspace, user=cls.user, role=WorkspaceMember.Role.OWNER)
        cls.model = Model.objects.create(workspace=cls.workspace, name="A model")

    def setUp(self):
        self.client.force_login(self.user)

    def test_the_dashboard_is_served_at_workspace(self):
        response = self.client.get("/workspace/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "A model")

    def test_the_dashboard_create_model_link_uses_the_named_route(self):
        response = self.client.get(reverse("workspace:index"))

        self.assertContains(response, f'href="{reverse("workspace:create_model")}"')
        self.assertNotContains(response, 'href="/create-model"')

    def test_the_old_root_paths_are_gone(self):
        self.assertEqual(self.client.get("/create-model").status_code, 404)

    def test_instantiating_a_template_returns_to_the_dashboard(self):
        url = reverse("workspace:model_template_review", args=[self.model.id, "business_process"])

        response = self.client.post(url)

        self.assertRedirects(response, reverse("workspace:index"), fetch_redirect_response=False)
        self.assertEqual(response["Location"], "/workspace/")

    def test_the_workspace_app_no_longer_hard_codes_the_old_root(self):
        """Prefer named URLs: no literal root redirect or /create-model link may creep back."""

        patterns = (
            re.compile(r"redirect\(\s*[\"']/[\"']\s*[,)]"),
            re.compile(r"HttpResponseRedirect\(\s*[\"']/[\"']"),
            re.compile(r"""(?:href|action)=["']/create-model"""),
            re.compile(r"""(?:href|action)=["']/["']"""),
        )
        offenders = []

        for path in list(WORKSPACE_APP.rglob("*.py")) + list(WORKSPACE_APP.rglob("*.html")):
            if "migrations" in path.parts or path.name == "tests.py":
                continue

            text = path.read_text(encoding="utf-8")

            for pattern in patterns:
                if pattern.search(text):
                    offenders.append(f"{path.name}: {pattern.pattern}")

        self.assertEqual(offenders, [])
