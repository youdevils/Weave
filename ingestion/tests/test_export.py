import json

from django.test import Client
from django.urls import reverse

from ingestion.tests.base import ImportTestCase


class ExportModelTests(ImportTestCase):

    def url(self, model=None):
        return reverse("ingestion:export_model", args=[(model or self.model).id])

    def _get(self, user):
        client = Client()
        client.force_login(user)
        return client.get(self.url())

    def test_owner_and_editor_can_download_the_export(self):
        for user in (self.owner, self.editor):
            response = self._get(user)

            self.assertEqual(response.status_code, 200, user.email)
            self.assertEqual(response["Content-Type"], "application/json")
            self.assertIn("attachment;", response["Content-Disposition"])
            self.assertIn(".json", response["Content-Disposition"])

    def test_a_viewer_cannot(self):
        self.assertEqual(self._get(self.viewer).status_code, 403)

    def test_a_member_of_another_workspace_gets_a_404(self):
        self.assertEqual(self._get(self.stranger).status_code, 404)

    def test_anonymous_users_are_sent_to_log_in(self):
        response = Client().get(self.url())

        self.assertEqual(response.status_code, 302)

    def test_the_export_contains_the_complete_canonical_model(self):
        app = self.make_app("One", app_id="A1", owner="Alice")
        other_app = self.make_app("Two", app_id="A2")
        self.make_uses(app, other_app, since="2024-01-01")

        payload = json.loads(self._get(self.editor).content)

        self.assertEqual(payload["format"], "onyxjar")
        self.assertEqual(payload["version"], 1)
        self.assertEqual(payload["model"]["name"], "Model")

        object_type_ids = {t["id"] for t in payload["objectTypes"]}
        object_type_names = {t["name"] for t in payload["objectTypes"]}
        self.assertEqual(object_type_names, {"Application", "Person"})

        app_type = next(t for t in payload["objectTypes"] if t["name"] == "Application")
        attribute_keys = {a["key"] for a in app_type["attributes"]}
        self.assertEqual(attribute_keys, {"app_id", "owner", "cost", "live", "go_live", "tier"})
        tier = next(a for a in app_type["attributes"] if a["key"] == "tier")
        self.assertEqual(tier["choices"], ["gold", "silver"])

        relationship_type_names = {t["name"] for t in payload["relationshipTypes"]}
        self.assertEqual(relationship_type_names, {"Uses"})
        uses_type = payload["relationshipTypes"][0]
        self.assertEqual(len(uses_type["rules"]), 1)
        rule = uses_type["rules"][0]
        self.assertIn(rule["subjectTypeId"], object_type_ids)
        self.assertIn(rule["objectTypeId"], object_type_ids)

        objects_by_name = {o["name"]: o for o in payload["objects"]}
        self.assertEqual(set(objects_by_name), {"One", "Two"})
        self.assertIn(objects_by_name["One"]["typeId"], object_type_ids)
        self.assertEqual(objects_by_name["One"]["attributes"]["owner"], "Alice")

        self.assertEqual(len(payload["relationships"]), 1)
        relationship = payload["relationships"][0]
        self.assertEqual(relationship["sourceId"], objects_by_name["One"]["id"])
        self.assertEqual(relationship["targetId"], objects_by_name["Two"]["id"])
        self.assertEqual(relationship["attributes"]["since"], "2024-01-01")

    def test_the_export_only_contains_this_models_data(self):
        self.make_app("One", app_id="A1")
        self.make_app("Elsewhere", app_id="B1", model=self.other_model, object_type=self.other_app_type)

        payload = json.loads(self._get(self.editor).content)

        self.assertEqual({o["name"] for o in payload["objects"]}, {"One"})
