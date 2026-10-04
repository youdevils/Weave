import json
import re
import uuid
from datetime import timezone

from django.conf import settings
from django.test import Client
from django.urls import reverse

from model.models.model import Model
from model.models.object_type import ObjectType
from model.services.appearance import AppearanceService
from publication.models import Publication
from publication.services import publishing
from publication.services.portable.validator import split_document
from workspace.models import Workspace, WorkspaceMember

from .base import PublicationTestCase


class ViewFixture(PublicationTestCase):

    def setUp(self):
        super().setUp()
        self.alice = self.make_object(self.person_type, "Alice", attributes={"status": "Active"})
        self.ops = self.make_object(self.team_type, "Ops")
        self.make_relationship(self.alice, self.ops)
        self.client.force_login(self.owner)

    def url(self, name, model=None):
        return reverse(f"publication:{name}", args=[(model or self.model).id])

    def publication_url(self, name, publication, model=None):
        return reverse(f"publication:{name}", args=[(model or self.model).id, publication.id])

    def post_json(self, name, body, client=None):
        return (client or self.client).post(self.url(name), data=json.dumps(body), content_type="application/json")

    def preview(self, config=None):
        response = self.post_json("publish_preview", {"config": config or {}})
        self.assertEqual(response.status_code, 200, response.content[:300])
        return response.json()

    def publish(self, config=None, expected=None, client=None):
        config = config if config is not None else {"title": "Board pack", "filename": "board.html"}
        if expected is None:
            data = self.preview(config)
            expected = {"revision": data["revision"], "digest": data["digest"]}
        return self.post_json("publish_submit", {"config": config, "expected": expected}, client)

    def publish_and_get(self, config=None, expected=None, client=None):
        """Publish (as the given client, defaulting to the owner) and return the created row."""
        response = self.publish(config, expected, client)
        self.assertEqual(response.status_code, 200, response.content[:300])
        return Publication.objects.get(id=response.json()["publication"]["id"])

    def client_for(self, user):
        client = Client()
        client.force_login(user)
        return client


class AccessTests(ViewFixture):
    """
    Publishing (creating a Publication) is Owner/Editor only; anyone outside the
    workspace gets 404. Looking at publications that already exist (the index, a
    hosted View, a Download) is not publishing: any member may use them - see
    ViewAndDownloadAccessTests below for those.
    """

    ENDPOINTS = (
        ("publish", "get"),
        ("publish_search", "get"),
        ("publish_preview", "post"),
        ("publish_submit", "post"),
    )

    def call(self, client, name, method, model=None):
        url = self.url(name, model)
        if method == "get":
            return client.get(url)
        return client.post(url, data="{}", content_type="application/json")

    def test_anonymous_users_are_sent_to_login(self):
        for name, method in self.ENDPOINTS + (("publication_history", "get"),):
            with self.subTest(name):
                response = self.call(Client(), name, method)
                self.assertEqual(response.status_code, 302)
                self.assertIn("login", response["Location"].lower())

    def test_owners_and_editors_can_open_the_page_and_the_publications_index(self):
        for user in (self.owner, self.editor):
            for name in ("publish", "publication_history"):
                with self.subTest(user=user.email, page=name):
                    self.assertEqual(self.client_for(user).get(self.url(name)).status_code, 200)

    def test_viewers_are_forbidden_from_publishing(self):
        client = self.client_for(self.viewer)
        for name, method in self.ENDPOINTS:
            with self.subTest(name):
                self.assertEqual(self.call(client, name, method).status_code, 403)

    def test_viewers_can_open_the_publications_index(self):
        self.assertEqual(self.client_for(self.viewer).get(self.url("publication_history")).status_code, 200)

    def test_a_viewer_cannot_publish(self):
        data = self.preview()

        response = self.publish(expected={"revision": data["revision"], "digest": data["digest"]}, client=self.client_for(self.viewer))

        self.assertEqual(response.status_code, 403)
        self.assertEqual(Publication.objects.count(), 0)

    def test_strangers_get_404_and_learn_nothing(self):
        client = self.client_for(self.stranger)
        for name, method in self.ENDPOINTS + (("publication_history", "get"),):
            with self.subTest(name):
                self.assertEqual(self.call(client, name, method).status_code, 404)

    def test_a_user_with_no_membership_at_all_gets_404(self):
        from account.models import CustomUser

        loner = CustomUser.objects.create_user(email="loner@example.com", password="test-password")

        self.assertEqual(self.call(self.client_for(loner), "publish", "get").status_code, 404)

    def test_membership_of_another_workspace_gives_no_access(self):
        # The stranger owns "Other Workspace"; this model belongs to a different one.
        other_model = Model.objects.create(workspace=self.other_workspace, name="Theirs", revision=1)

        self.assertEqual(self.client_for(self.stranger).get(self.url("publish", other_model)).status_code, 200)
        self.assertEqual(self.client_for(self.stranger).get(self.url("publish")).status_code, 404)
        self.assertEqual(self.client.get(self.url("publish", other_model)).status_code, 404)

    def test_a_user_in_several_workspaces_is_checked_against_the_models_own_workspace(self):
        second = Workspace.objects.create(name="Second")
        WorkspaceMember.objects.create(workspace=second, user=self.editor, role=WorkspaceMember.Role.VIEWER)
        # The editor is an EDITOR in the model's workspace, a VIEWER elsewhere: the model's workspace decides.
        self.assertEqual(self.client_for(self.editor).get(self.url("publish")).status_code, 200)

    def test_unknown_models_are_404(self):
        response = self.client.get(reverse("publication:publish", args=[uuid.uuid4()]))

        self.assertEqual(response.status_code, 404)

    def test_wrong_methods_are_rejected(self):
        self.assertEqual(self.client.post(self.url("publish")).status_code, 405)
        self.assertEqual(self.client.get(self.url("publish_preview")).status_code, 405)
        self.assertEqual(self.client.get(self.url("publish_submit")).status_code, 405)
        self.assertEqual(self.client.post(self.url("publish_search")).status_code, 405)

    def test_posts_require_a_csrf_token(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.owner)

        response = client.post(self.url("publish_submit"), data="{}", content_type="application/json")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(Publication.objects.count(), 0)


class PageTests(ViewFixture):

    def bootstrap(self, response):
        text = re.search(r'<script id="publish-bootstrap" type="application/json">(.*?)</script>', response.content.decode(), re.S).group(1)
        return json.loads(text)

    def test_the_page_carries_the_defaults_and_the_canonical_facets(self):
        response = self.client.get(self.url("publish"))

        self.assertEqual(response.status_code, 200)
        data = self.bootstrap(response)
        self.assertEqual(data["revision"], self.model.revision)
        self.assertEqual(data["config"]["title"], "Test Model")
        self.assertIsNone(data["previous"])
        self.assertEqual({t["name"] for t in data["facets"]["objectTypes"]}, {"Person", "Team"})
        self.assertEqual(data["urls"]["preview"], self.url("publish_preview"))
        self.assertEqual(data["depth"], {"default": 1, "max": 5})

    def test_facets_describe_the_whole_canonical_model_not_a_pending_proposal(self):
        proposal = self.working_proposal()
        self.propose_object(proposal, self.person_type.id, "Proposed Pat")

        data = self.bootstrap(self.client.get(self.url("publish")))

        person = next(t for t in data["facets"]["objectTypes"] if t["name"] == "Person")
        self.assertEqual(person["count"], 1)

    def test_the_next_page_starts_from_the_last_publication(self):
        self.publish({"title": "Quarterly", "filename": "q.html", "presentation": {"theme_colour": "#123456"}})

        data = self.bootstrap(self.client.get(self.url("publish")))

        self.assertEqual(data["config"]["title"], "Quarterly")
        self.assertEqual(data["config"]["filename"], "q.html")
        self.assertEqual(data["config"]["presentation"]["theme_colour"], "#123456")
        self.assertEqual(data["previous"]["sequence"], 1)

    def test_stale_defaults_are_reported_not_fatal(self):
        stale = str(uuid.uuid4())
        self.make_publication(
            scope={"object_types": {"excluded": [stale]}, "traversal": {"roots": [stale], "depth": 1}}
        )

        response = self.client.get(self.url("publish"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual({n["kind"] for n in self.bootstrap(response)["notices"]}, {"object_type", "object"})

    def test_the_page_states_what_a_publication_contains(self):
        html = self.client.get(self.url("publish")).content.decode()

        self.assertIn("proposed changes are never included", html)
        self.assertIn("email address", html)
        self.assertIn('id="publish-button"', html)

    def test_the_page_is_settings_then_scope_then_preview(self):
        html = self.client.get(self.url("publish")).content.decode()

        order = [html.index(marker) for marker in ('id="publish-settings-title"', 'id="publish-scope"', 'id="model-explorer"')]
        self.assertEqual(order, sorted(order))
        # The scope controls come in the agreed order.
        controls = [
            html.index(marker)
            for marker in ('id="publish-start-title"', 'id="publish-object-type-rows"', 'id="publish-relationship-type-rows"', 'id="publish-filters-title"')
        ]
        self.assertEqual(controls, sorted(controls))
        # Publication details and the opening view live in the settings, above the scope panel.
        for marker in ('id="publish-title"', 'id="publish-theme-colour"', 'id="publish-opening-set"'):
            self.assertLess(html.index(marker), html.index('id="publish-scope"'))
        # The Publish button stays in the page header, above the scope panel.
        self.assertLess(html.index('id="publish-button"'), html.index('id="publish-scope"'))
        # What will be published (the summary line, then the applied-scope
        # chips) sits at the top of the preview, above what the viewer is
        # currently showing (the explorer's own counts and selection) --
        # not in the scope panel, whose own filter lists can grow long.
        preview_order = [
            html.index(marker)
            for marker in (
                'id="publish-scope"',
                'id="model-explorer"',
                'id="publish-summary"',
                'id="publish-scope-chips-toggle"',
                'id="publish-clear-scope"',
                'id="publish-scope-chips"',
                'id="explorer-counts"',
                'id="explorer-chips"',
                'id="model-explorer-graph"',
            )
        ]
        self.assertEqual(preview_order, sorted(preview_order))
        # The collapse toggle is wired up correctly.
        self.assertIn('data-action="toggle-scope-chips"', html)
        self.assertIn('aria-expanded="true"', html)
        self.assertIn('aria-controls="publish-scope-chips"', html)

    def test_the_preview_keeps_what_the_explorer_needs_and_drops_the_explorer_panels(self):
        html = self.client.get(self.url("publish")).content.decode()

        for retained in ("model-explorer", "model-explorer-graph", "explorer-counts", "explorer-chips", "explorer-notices", "explorer-error"):
            self.assertIn(f'id="{retained}"', html)
        for dropped in ("explorer-legend", "explorer-details", "explorer-search", "explorer-filter-builder"):
            self.assertNotIn(f'id="{dropped}"', html)
        self.assertNotIn("Reader controls", html)
        self.assertNotIn('data-action="fit-view"', html)
        self.assertNotIn('data-action="reset-view"', html)

    def test_the_type_selectors_offer_all_and_are_independently_collapsible(self):
        html = self.client.get(self.url("publish")).content.decode()

        for kind in ("object", "relationship"):
            self.assertIn(f'id="publish-{kind}-type-toggle"', html)
            self.assertIn(f'data-action="select-all-{kind}-types"', html)
            self.assertIn(f'id="publish-select-all-{kind}-types"', html)
        self.assertNotIn('id="publish-scope-toggle"', html)

    def test_inactive_records_and_types_follow_the_publishing_rules_in_the_page_facets(self):
        legacy = ObjectType.objects.create(model=self.model, name="Legacy", key="legacy", is_active=False)
        self.make_object(legacy, "Old thing", is_active=False)
        ObjectType.objects.create(model=self.model, name="Place", key="place", is_active=True)
        self.team_type.is_active = False  # inactive, but Ops (from the fixture) is an active team
        self.team_type.save()
        self.make_object(self.person_type, "Dormant", is_active=False)

        types = {t["name"]: t for t in self.bootstrap(self.client.get(self.url("publish")))["facets"]["objectTypes"]}

        self.assertNotIn("Legacy", types)  # inactive, nothing active in it
        self.assertEqual(types["Team"]["count"], 1)  # inactive, but still holds an active record
        self.assertEqual(types["Person"]["count"], 1)  # the inactive Dormant is not counted
        self.assertEqual(types["Place"]["count"], 0)  # active type without records: still listed

    def test_the_publishing_sidebar_replaces_the_model_sidebar(self):
        html = self.client.get(self.url("publish")).content.decode()
        start = html.index('<aside class="model-sidebar publication-sidebar"')
        sidebar = html[start : html.index("</aside>", start)]

        self.assertIn("Publishing", sidebar)
        self.assertIn(">Publish<", sidebar.replace(" ", "").replace("\n", ""))
        self.assertIn("View Publications", sidebar)
        self.assertIn(reverse("model:overview", args=[self.model.id]), sidebar)
        self.assertIn(reverse("publication:publication_history", args=[self.model.id]), sidebar)
        self.assertNotIn("Define model", sidebar)
        self.assertNotIn("Proposals", sidebar)
        self.assertRegex(sidebar, r'class="model-nav-item active"[^>]*aria-current="page"')

    def test_the_index_lists_no_publications_yet(self):
        response = self.client.get(self.url("publication_history"))

        self.assertContains(response, "Publications")
        self.assertContains(response, "No publications yet")
        self.assertContains(response, 'class="model-nav-item active"')

    def test_the_index_lists_publications_newest_first_with_view_and_download_links(self):
        first = self.publish_and_get({"title": "First", "filename": "first.html"})
        self.model.revision += 1
        self.model.save(update_fields=["revision"])
        second = self.publish_and_get({"title": "Second", "filename": "second.html"})

        html = self.client.get(self.url("publication_history")).content.decode()

        self.assertLess(html.index("Second"), html.index("First"))
        for publication in (first, second):
            self.assertIn(self.publication_url("publication_view", publication), html)
            self.assertIn(self.publication_url("publication_download", publication), html)

    def test_only_owners_and_editors_see_the_publish_call_to_action_on_the_index(self):
        self.publish_and_get()

        owner_html = self.client_for(self.owner).get(self.url("publication_history")).content.decode()
        viewer_html = self.client_for(self.viewer).get(self.url("publication_history")).content.decode()

        # The sidebar's own "Publish" link is shown to everyone who can reach this page at all
        # (the publish page itself still enforces the real gate); it's the index's own call to
        # action - which a Viewer would only ever see 403 behind - that should be role-aware.
        self.assertIn('id="publications-publish-cta"', owner_html)
        self.assertNotIn('id="publications-publish-cta"', viewer_html)

    def test_the_page_loads_nothing_that_edits_the_model(self):
        html = self.client.get(self.url("publish")).content.decode()

        self.assertNotIn("model_editing.js", html)
        self.assertNotIn("proposal.js", html)
        self.assertNotIn("appearance-form.js", html)


class ModelSidebarTests(ViewFixture):

    def test_the_model_sidebar_links_to_publishing(self):
        html = self.client.get(reverse("model:overview", args=[self.model.id])).content.decode()

        self.assertIn(f'href="{self.url("publish")}"', html)
        self.assertIn(f'href="{self.url("publication_history")}"', html)


class SearchTests(ViewFixture):

    def test_search_finds_canonical_objects(self):
        data = self.client.get(self.url("publish_search"), {"q": "ali"}).json()

        self.assertTrue(data["success"])
        self.assertEqual([r["name"] for r in data["results"]], ["Alice"])
        self.assertIsNone(data["results"][0]["inView"])

    def test_search_never_returns_proposed_objects(self):
        proposal = self.working_proposal()
        self.propose_object(proposal, self.person_type.id, "Proposed Pat")

        data = self.client.get(self.url("publish_search"), {"q": "pat"}).json()

        self.assertEqual(data["results"], [])

    def test_search_is_scoped_to_the_model(self):
        other = Model.objects.create(workspace=self.workspace, name="Other", revision=1)
        other_type = other.object_types.create(name="Thing", key="thing")
        other.model_objects.create(object_type=other_type, name="Alicia Elsewhere")

        data = self.client.get(self.url("publish_search"), {"q": "alic"}).json()

        self.assertEqual([r["name"] for r in data["results"]], ["Alice"])

    def test_an_empty_query_returns_nothing(self):
        data = self.client.get(self.url("publish_search"), {"q": "  "}).json()

        self.assertEqual(data["results"], [])


class PreviewViewTests(ViewFixture):

    def test_the_preview_returns_the_bundle_summary_and_digest(self):
        data = self.preview({"scope": {"object_types": {"excluded": [str(self.team_type.id)]}}})

        self.assertTrue(data["success"])
        self.assertEqual(data["revision"], self.model.revision)
        self.assertEqual(data["summary"], {"objects": 1, "relationships": 0, "totalObjects": 2, "totalRelationships": 1})
        self.assertEqual([o["name"] for o in data["bundle"]["dataset"]["objects"]], ["Alice"])
        self.assertEqual(data["bundle"]["digest"], data["digest"])
        self.assertEqual(data["config"]["scope"]["object_types"]["excluded"], [str(self.team_type.id)])

    def test_the_preview_names_the_starting_objects(self):
        data = self.preview({"scope": {"traversal": {"roots": [str(self.alice.id)], "depth": 1}}})

        self.assertEqual(data["roots"], {str(self.alice.id): {"name": "Alice", "typeName": "Person"}})
        self.assertEqual(sorted(o["name"] for o in data["bundle"]["dataset"]["objects"]), ["Alice", "Ops"])

    def test_the_preview_reports_and_repairs_stale_settings(self):
        data = self.preview({"scope": {"object_types": {"excluded": [str(uuid.uuid4())]}}})

        self.assertEqual([n["kind"] for n in data["notices"]], ["object_type"])
        self.assertEqual(data["config"]["scope"]["object_types"]["excluded"], [])

    def test_the_preview_writes_nothing(self):
        self.preview()

        self.assertEqual(Publication.objects.count(), 0)

    def test_malformed_bodies_are_400(self):
        for body in ("not json", "[]", '"x"'):
            with self.subTest(body=body):
                response = self.client.post(self.url("publish_preview"), data=body, content_type="application/json")
                self.assertEqual(response.status_code, 400)
                self.assertFalse(response.json()["success"])

    def test_a_definition_that_is_not_an_object_is_400(self):
        response = self.post_json("publish_preview", {"config": "nope"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "invalid")

    def test_ids_from_another_model_are_dropped_not_followed(self):
        other = Model.objects.create(workspace=self.other_workspace, name="Theirs", revision=1)
        other_type = other.object_types.create(name="Secret", key="secret")
        foreign = other.model_objects.create(object_type=other_type, name="Foreign Secret")

        data = self.preview({"scope": {"traversal": {"roots": [str(foreign.id)], "depth": 1}, "object_types": {"excluded": [str(other_type.id)]}}})

        self.assertEqual({n["kind"] for n in data["notices"]}, {"object", "object_type"})
        self.assertNotIn("Foreign Secret", json.dumps(data))


class SubmitResponseTests(ViewFixture):
    """publish_submit reports identity and URLs; it no longer sends the document itself."""

    def test_publishing_reports_the_new_publications_identity_and_urls(self):
        response = self.publish({"title": "Board pack", "filename": "board.html"})
        publication = Publication.objects.get()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(
            data["publication"],
            {
                "id": str(publication.id),
                "sequence": publication.sequence,
                "title": "Board pack",
                "revision": publication.source_revision,
                "publishedAt": publication.published_at.isoformat(),
            },
        )
        self.assertEqual(data["urls"]["view"], self.publication_url("publication_view", publication))
        self.assertEqual(data["urls"]["download"], self.publication_url("publication_download", publication))
        self.assertEqual(data["urls"]["index"], self.url("publication_history"))

    def test_the_document_is_not_sent_back(self):
        response = self.publish()

        self.assertNotIn("<!DOCTYPE html>", response.content.decode())
        self.assertNotIn("X-Publication-Id", response.headers)

    def test_the_file_is_not_written_to_disk(self):
        import os

        self.publish()

        self.assertFalse(settings.MEDIA_ROOT and os.path.exists(settings.MEDIA_ROOT))


class ViewAndDownloadAccessTests(ViewFixture):
    """
    The index, hosted View and Download are all "view" capabilities: any member of
    the model's workspace may use them, unlike Publish itself.
    """

    def setUp(self):
        super().setUp()
        self.publication = self.publish_and_get({"title": "Board pack", "filename": "board.html"})

    def test_any_member_can_view_and_download(self):
        for user in (self.owner, self.editor, self.viewer):
            for name in ("publication_view", "publication_download"):
                with self.subTest(user=user.email, page=name):
                    client = self.client_for(user)
                    response = client.get(self.publication_url(name, self.publication))
                    self.assertEqual(response.status_code, 200)

    def test_strangers_get_404_and_learn_nothing(self):
        client = self.client_for(self.stranger)
        for name in ("publication_view", "publication_download"):
            with self.subTest(name):
                self.assertEqual(client.get(self.publication_url(name, self.publication)).status_code, 404)

    def test_anonymous_users_are_sent_to_login(self):
        for name in ("publication_view", "publication_download"):
            with self.subTest(name):
                response = Client().get(self.publication_url(name, self.publication))
                self.assertEqual(response.status_code, 302)
                self.assertIn("login", response["Location"].lower())

    def test_a_publication_id_from_another_model_is_404(self):
        other_model = Model.objects.create(workspace=self.workspace, name="Other model", revision=1)

        for name in ("publication_view", "publication_download"):
            with self.subTest(name):
                response = self.client.get(self.publication_url(name, self.publication, model=other_model))
                self.assertEqual(response.status_code, 404)


class ViewViewTests(ViewFixture):

    def test_the_hosted_view_embeds_the_stored_bundle(self):
        publication = self.publish_and_get({"title": "Board pack", "filename": "b.html"})

        html = self.client.get(self.publication_url("publication_view", publication)).content.decode()

        self.assertIn("Board pack", html)
        self.assertIn(f"Revision {publication.source_revision}", html)
        text = re.search(
            r'<script id="onyxjar-published-data" type="application/json">(.*?)</script>', html, re.S
        ).group(1)
        self.assertEqual(json.loads(text), publication.bundle)

    def test_the_view_shows_the_stored_snapshot_not_the_current_model(self):
        publication = self.publish_and_get()
        self.make_object(self.person_type, "Added after publishing")

        html = self.client.get(self.publication_url("publication_view", publication)).content.decode()

        self.assertNotIn("Added after publishing", html)

    def test_a_publication_with_no_stored_snapshot_is_unavailable(self):
        legacy = self.make_publication()  # bundle defaults to {} - predates snapshot storage

        response = self.client.get(self.publication_url("publication_view", legacy))

        self.assertEqual(response.status_code, 404)
        self.assertContains(response, "not available", status_code=404)


class DownloadViewTests(ViewFixture):

    def test_downloading_returns_the_file_as_an_attachment(self):
        publication = self.publish_and_get({"title": "Board pack", "filename": "board.html"})

        response = self.client.get(self.publication_url("publication_download", publication))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/html; charset=utf-8")
        self.assertEqual(response["Content-Disposition"], 'attachment; filename="board.html"')
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        html = response.content.decode()
        self.assertTrue(html.startswith("<!DOCTYPE html>"))
        self.assertEqual(len(split_document(html)["data"]), 1)

    def test_the_response_identifies_the_publication(self):
        publication = self.publish_and_get()

        response = self.client.get(self.publication_url("publication_download", publication))

        self.assertEqual(response["X-Publication-Id"], str(publication.id))
        self.assertEqual(response["X-Publication-Sequence"], str(publication.sequence))
        self.assertEqual(response["X-Publication-Revision"], str(publication.source_revision))
        self.assertEqual(
            response["X-Publication-Published-At"], publication.published_at.astimezone(timezone.utc).isoformat()
        )

    def test_a_hostile_filename_is_made_safe(self):
        publication = self.publish_and_get({"title": "T", "filename": '../../etc/pass"wd\r\nX-Evil: 1'})

        response = self.client.get(self.publication_url("publication_download", publication))

        self.assertEqual(response.status_code, 200)
        disposition = response["Content-Disposition"]
        self.assertNotIn("..", disposition)
        self.assertNotIn("/", disposition)
        self.assertNotIn("\n", disposition)
        self.assertNotIn("X-Evil", response.headers)
        self.assertTrue(disposition.rstrip('"').endswith(".html"))

    def test_a_non_ascii_filename_is_encoded_for_the_header(self):
        publication = self.publish_and_get({"title": "T", "filename": "Übersicht Straße.html"})

        response = self.client.get(self.publication_url("publication_download", publication))

        self.assertIn("filename*=", response["Content-Disposition"])

    def test_the_file_is_not_written_to_disk(self):
        import os

        publication = self.publish_and_get()
        self.client.get(self.publication_url("publication_download", publication))

        self.assertFalse(settings.MEDIA_ROOT and os.path.exists(settings.MEDIA_ROOT))

    def test_the_document_embeds_the_publication_context(self):
        publication = self.publish_and_get({"title": "Board pack", "filename": "b.html"})

        html = self.client.get(self.publication_url("publication_download", publication)).content.decode()

        self.assertIn("<title>Board pack</title>", html)
        self.assertIn(f"Revision {publication.source_revision}", html)
        self.assertIn(str(publication.id), html)

    def test_downloading_an_old_publication_reproduces_it_not_the_current_model(self):
        first = self.publish_and_get({"title": "First", "filename": "first.html"})
        self.model.revision += 1
        self.model.save(update_fields=["revision"])
        self.make_object(self.person_type, "Added after First was published")
        self.publish_and_get({"title": "Second", "filename": "second.html"})

        html = self.client.get(self.publication_url("publication_download", first)).content.decode()

        self.assertIn("<title>First</title>", html)
        self.assertNotIn("Added after First was published", html)

    def test_a_publication_with_no_stored_snapshot_cannot_be_downloaded(self):
        legacy = self.make_publication()

        response = self.client.get(self.publication_url("publication_download", legacy))

        self.assertEqual(response.status_code, 404)


class RefusalTests(ViewFixture):

    def test_publishing_needs_a_preview(self):
        response = self.post_json("publish_submit", {"config": {}})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "invalid")
        self.assertEqual(Publication.objects.count(), 0)

    def test_a_model_change_since_the_preview_is_a_409_with_the_new_revision(self):
        data = self.preview()
        self.model.revision += 1
        self.model.save(update_fields=["revision"])

        response = self.post_json("publish_submit", {"config": {}, "expected": {"revision": data["revision"], "digest": data["digest"]}})

        self.assertEqual(response.status_code, 409)
        body = response.json()
        self.assertEqual((body["success"], body["code"], body["revision"]), (False, "changed", self.model.revision))
        self.assertEqual(Publication.objects.count(), 0)

    def test_an_appearance_change_since_the_preview_is_a_409(self):
        data = self.preview()
        AppearanceService.update_customisation(self.model, "object", "background", "#ff0000")

        response = self.post_json("publish_submit", {"config": {}, "expected": {"revision": data["revision"], "digest": data["digest"]}})

        self.assertEqual(response.status_code, 409)
        self.assertEqual(Publication.objects.count(), 0)

    def test_a_generation_failure_is_a_500_that_leaks_nothing_and_stores_nothing(self):
        from unittest import mock

        data = self.preview()

        with mock.patch.object(publishing, "render_document", side_effect=RuntimeError("secret internals")):
            response = self.post_json("publish_submit", {"config": {}, "expected": {"revision": data["revision"], "digest": data["digest"]}})

        self.assertEqual(response.status_code, 500)
        self.assertNotIn("secret internals", response.content.decode())
        self.assertEqual(response.json()["code"], "generation_failed")
        self.assertEqual(Publication.objects.count(), 0)

    def test_an_oversized_publication_is_a_422(self):
        from django.test import override_settings

        data = self.preview()

        with override_settings(PUBLICATION_MAX_OBJECTS=1):
            response = self.post_json("publish_submit", {"config": {}, "expected": {"revision": data["revision"], "digest": data["digest"]}})

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "too_large")
        self.assertEqual(Publication.objects.count(), 0)
