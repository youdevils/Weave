import json

from django.test import Client
from django.urls import reverse

from account.models import CustomUser
from publication.services import publishing

from .base import PublicationTestCase


class PublicationEntitlementTests(PublicationTestCase):
    """
    Publication creation is plan-gated (user_can_publish), independently of
    the Owner/Editor workspace-role gate already covered elsewhere
    (publication.tests.test_views.AccessTests). Viewing/downloading an
    already-created Publication is untouched by this and stays ungated.
    """

    def setUp(self):
        super().setUp()
        # base.py defaults owner/editor to Communicator so every *other* test
        # in this app can publish without thinking about plans -- these tests
        # are specifically about the entitlement, so they set it explicitly.
        self.owner.plan = CustomUser.Plan.LEARNER
        self.owner.save(update_fields=["plan"])
        self.client.force_login(self.owner)

    def url(self, name):
        return reverse(f"publication:{name}", args=[self.model.id])

    def post_json(self, name, body):
        return self.client.post(self.url(name), data=json.dumps(body), content_type="application/json")

    def test_learner_owner_cannot_publish_via_the_service(self):
        with self.assertRaises(publishing.PublicationEntitlementDenied):
            publishing.publish(self.model.id, self.owner, {"title": "x", "filename": "x.html"}, {"revision": 0, "digest": "0" * 64})

    def test_communicator_owner_can_publish_via_the_service(self):
        self.owner.plan = CustomUser.Plan.COMMUNICATOR
        self.owner.save(update_fields=["plan"])

        canonical = self.canonical()
        result = self.normalised({"title": "Board pack", "filename": "board.html"})
        bundle = publishing.build_bundle(self.model, result.published, result.config)
        expected = {"revision": self.model.revision, "digest": bundle["digest"]}

        artifact = publishing.publish(self.model.id, self.owner, {"title": "Board pack", "filename": "board.html"}, expected)

        self.assertIsNotNone(artifact.publication.id)

    def test_learner_owner_gets_entitlement_denied_from_publish_submit(self):
        response = self.post_json(
            "publish_submit",
            {"config": {"title": "x", "filename": "x.html"}, "expected": {"revision": 0, "digest": "0" * 64}},
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "entitlement_denied")

    def test_learner_owner_sees_the_unavailable_page(self):
        response = self.client.get(self.url("publish"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "publication/publish_unavailable.html")
        self.assertContains(response, "Publishing is available on the Communicator plan.")

    def test_communicator_owner_sees_the_publish_page(self):
        self.owner.plan = CustomUser.Plan.COMMUNICATOR
        self.owner.save(update_fields=["plan"])

        response = self.client.get(self.url("publish"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "publication/publish.html")

    def test_viewing_an_existing_publication_stays_ungated_for_a_learner(self):
        publication = self.make_publication()

        response = self.client.get(
            reverse("publication:publication_view", args=[self.model.id, publication.id])
        )

        self.assertNotEqual(response.status_code, 403)
