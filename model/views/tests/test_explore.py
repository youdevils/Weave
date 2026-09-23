import json
import uuid

from django.test import TestCase
from django.urls import reverse

from account.models import CustomUser
from model.models.evidence_reference import EvidenceReference
from model.models.model import Model
from model.models.object import Object
from model.models.proposal import Proposal, ProposalChange
from model.models.proposal_submission_result import ProposalSubmissionResult
from model.models.relationship import Relationship
from model.services.appearance import OBJECT_TYPE, AppearanceService
from model.services.model_graph.tests.base import ModelGraphTestCase
from model.views.tests.proposal_test_utils import activate_proposal
from workspace.models import Workspace, WorkspaceMember

AMBER = "#F08C00"


class ExploreViewTestCase(ModelGraphTestCase):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        WorkspaceMember.objects.create(workspace=cls.workspace, user=cls.user, role=WorkspaceMember.Role.OWNER)

        cls.other_workspace = Workspace.objects.create(name="Other Workspace")
        cls.other_user = CustomUser.objects.create_user(email="other@example.com", password="test-password")
        WorkspaceMember.objects.create(
            workspace=cls.other_workspace, user=cls.other_user, role=WorkspaceMember.Role.OWNER
        )

    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)
        self.alice = self.make_object(self.person_type, "Alice", attributes={"status": "Active"})
        self.alice_two = self.make_object(self.person_type, "Alice", attributes={"status": "Left"})
        self.ops = self.make_object(self.team_type, "Ops")
        self.membership = self.make_relationship(self.alice, self.ops)

    # -- urls -----------------------------------------------------------------

    def page_url(self):
        return reverse("model:explore", args=[self.model.id])

    def graph_url(self, **params):
        return self.with_params(reverse("model:explore_graph", args=[self.model.id]), params)

    def search_url(self, q, **params):
        return self.with_params(reverse("model:explore_search", args=[self.model.id]), {"q": q, **params})

    def object_url(self, object_id, **params):
        return self.with_params(reverse("model:explore_object", args=[self.model.id, object_id]), params)

    def relationship_url(self, relationship_id, **params):
        return self.with_params(reverse("model:explore_relationship", args=[self.model.id, relationship_id]), params)

    def with_params(self, url, params):
        from urllib.parse import urlencode

        return f"{url}?{urlencode(params, doseq=True)}" if params else url

    def all_urls(self):
        return [
            self.page_url(),
            self.graph_url(),
            self.search_url("alice"),
            self.object_url(self.alice.id),
            self.relationship_url(self.membership.id),
        ]

    def node_ids(self, response):
        return {n["id"] for n in response.json()["payload"]["nodes"]}


class AccessBoundaryTests(ExploreViewTestCase):

    def test_anonymous_users_are_redirected_to_login(self):
        self.client.logout()

        for url in self.all_urls():
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302, url)
            self.assertIn("login", response["Location"], url)

    def test_users_of_other_workspaces_get_404_everywhere(self):
        self.client.force_login(self.other_user)

        for url in self.all_urls():
            self.assertEqual(self.client.get(url).status_code, 404, url)

    def test_a_user_without_any_workspace_gets_404(self):
        loner = CustomUser.objects.create_user(email="loner@example.com", password="test-password")
        self.client.force_login(loner)

        for url in self.all_urls():
            self.assertEqual(self.client.get(url).status_code, 404, url)

    def test_another_models_objects_are_not_reachable_through_this_model(self):
        other = Model.objects.create(workspace=self.workspace, name="Other", revision=1)
        from model.models.object_type import ObjectType

        other_type = ObjectType.objects.create(model=other, name="Thing", key="thing", is_active=True)
        foreign = Object.objects.create(model=other, object_type=other_type, name="Foreign")

        self.assertEqual(self.client.get(self.object_url(foreign.id)).status_code, 404)
        self.assertNotIn(str(foreign.id), self.node_ids(self.client.get(self.graph_url())))

    def test_every_endpoint_is_read_only(self):
        for url in self.all_urls():
            for method in ("post", "put", "patch", "delete"):
                self.assertEqual(getattr(self.client, method)(url).status_code, 405, (method, url))


class ReadOnlyGuaranteeTests(ExploreViewTestCase):

    def snapshot(self):
        model = Model.objects.get(pk=self.model.pk)
        return {
            "proposals": Proposal.objects.count(),
            "changes": list(ProposalChange.objects.order_by("id").values_list("id", "after")),
            "evidence": list(
                EvidenceReference.objects.order_by("id").values_list("id", "change_id", "source", "locator", "note")
            ),
            "objects": list(Object.objects.order_by("id").values_list("id", "name", "attributes", "is_active")),
            "relationships": list(Relationship.objects.order_by("id").values_list("id", "is_active")),
            "revision": model.revision,
            "updated_at": model.updated_at,
        }

    def test_exploring_changes_nothing(self):
        proposal = self.working_proposal()
        self.propose_object(proposal, self.person_type.id, "Draft")
        activate_proposal(self.client, self.model.id, proposal)
        before = self.snapshot()

        for url in self.all_urls():
            self.client.get(url)
        self.client.get(self.graph_url(hide_objects=str(self.team_type.id), include=str(self.ops.id)))
        self.client.get(self.search_url("alice"))
        self.client.get(self.object_url(uuid.uuid4()))

        self.assertEqual(self.snapshot(), before)

    def test_search_does_not_alter_the_model_or_proposal(self):
        before = self.snapshot()

        self.client.get(self.search_url("a"))

        self.assertEqual(self.snapshot(), before)


class PageTests(ExploreViewTestCase):

    def test_page_renders_with_bootstrap_data(self):
        response = self.client.get(self.page_url())

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "model/explore.html")
        bootstrap = response.context["explorer_bootstrap"]
        self.assertEqual(len(bootstrap["graph"]["payload"]["nodes"]), 3)
        self.assertEqual(bootstrap["graph"]["summary"]["totalObjects"], 3)
        self.assertEqual({t["name"] for t in bootstrap["facets"]["objectTypes"]}, {"Person", "Team"})
        self.assertIn("graph", bootstrap["urls"])
        self.assertContains(response, 'id="model-explorer-bootstrap"')
        self.assertContains(response, 'id="explorer-search"')
        self.assertEqual(response.context["canvas_background"], "#FFFFFF")

    def test_sidebar_explore_link_is_real_and_active(self):
        response = self.client.get(self.page_url())
        html = response.content.decode()

        understand = html[html.index("Understand") : html.index("Define")]
        self.assertIn(f'href="{self.page_url()}"', understand)
        self.assertRegex(understand, r'model-nav-item\s+active\s+"\s*>\s*<span>Explore</span>')
        self.assertNotIn("collapsed", understand)

    def test_other_pages_link_to_explore_without_marking_it_active(self):
        html = self.client.get(reverse("model:overview", args=[self.model.id])).content.decode()

        self.assertIn(f'href="{self.page_url()}"', html)
        self.assertNotRegex(html, r'model-nav-item\s+active\s+"\s*>\s*<span>Explore</span>')

    def test_empty_model_renders(self):
        empty = Model.objects.create(workspace=self.workspace, name="Empty", revision=1)
        response = self.client.get(reverse("model:explore", args=[empty.id]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["explorer_bootstrap"]["graph"]["payload"]["nodes"], [])
        self.assertFalse(response.context["explorer_has_data"])

    def test_page_shows_canonical_state_without_an_active_proposal(self):
        proposal = self.working_proposal()
        self.propose_object(proposal, self.person_type.id, "Draft")

        response = self.client.get(self.page_url())

        names = {n["label"] for n in response.context["explorer_bootstrap"]["graph"]["payload"]["nodes"]}
        self.assertNotIn("Draft", names)
        self.assertFalse(response.context["explorer_bootstrap"]["hasProposal"])
        self.assertNotContains(response, "including your active proposal")

    def test_page_includes_the_active_proposal(self):
        proposal = self.working_proposal()
        self.propose_object(proposal, self.person_type.id, "Draft")
        activate_proposal(self.client, self.model.id, proposal)

        response = self.client.get(self.page_url())

        names = {n["label"] for n in response.context["explorer_bootstrap"]["graph"]["payload"]["nodes"]}
        self.assertIn("Draft", names)
        self.assertTrue(response.context["explorer_bootstrap"]["hasProposal"])
        self.assertContains(response, "including your active proposal")

    def test_legend_swatches_match_the_graph_nodes_for_shape_and_icon(self):
        AppearanceService.set_type_style(self.model, OBJECT_TYPE, self.person_type.id, "shape", "hexagon")
        AppearanceService.set_type_style(self.model, OBJECT_TYPE, self.team_type.id, "icon", "organisation")
        AppearanceService.set_type_style(self.model, OBJECT_TYPE, self.team_type.id, "border", "#AA0000")

        bootstrap = self.client.get(self.page_url()).context["explorer_bootstrap"]

        swatches = {t["id"]: t["swatch"] for t in bootstrap["facets"]["objectTypes"]}
        nodes = {n["data"]["object_type_id"]: n["style"] for n in bootstrap["graph"]["payload"]["nodes"]}

        person, team = str(self.person_type.id), str(self.team_type.id)
        # Shape types: the legend shape is the node shape and there is no image.
        self.assertEqual(swatches[person]["shape"], "hexagon")
        self.assertEqual(swatches[person]["shape"], nodes[person]["shape"])
        self.assertIsNone(swatches[person]["image"])
        # Icon types: the legend shows the same glyph the node draws, in the same colours.
        self.assertEqual(swatches[team]["icon"], "organisation")
        self.assertEqual(nodes[team]["shape"], "circularImage")
        self.assertEqual(swatches[team]["image"], nodes[team]["image"])
        for key in ("background", "border"):
            self.assertEqual(swatches[team][key], nodes[team][key])

    def test_legend_keeps_relationship_colour_and_line_style(self):
        AppearanceService.set_type_style(self.model, "relationship_type", self.member_of.id, "colour", "#c92a2a")
        AppearanceService.set_type_style(self.model, "relationship_type", self.member_of.id, "line_style", "dashed")

        bootstrap = self.client.get(self.page_url()).context["explorer_bootstrap"]

        (member_of,) = bootstrap["facets"]["relationshipTypes"]
        self.assertEqual(
            member_of["swatch"],
            {"colour": "#C92A2A", "lineStyle": "dashed", "colourSource": "type", "colourAttribute": None},
        )

    def test_proposed_change_legend_item_is_only_present_with_an_active_proposal(self):
        self.assertNotContains(self.client.get(self.page_url()), "Proposed change")

        proposal = self.working_proposal()
        self.propose_object(proposal, self.person_type.id, "Draft")
        activate_proposal(self.client, self.model.id, proposal)

        response = self.client.get(self.page_url())
        self.assertContains(response, "Proposed change")
        self.assertContains(response, "model-ontology-legend-swatch-proposed")

    def test_page_reflects_model_customisation(self):
        AppearanceService.update_customisation(self.model, "theme", "canvas_background", "#101010")

        response = self.client.get(self.page_url())

        self.assertEqual(response.context["canvas_background"], "#101010")
        self.assertContains(response, "background: #101010;")


class GraphEndpointTests(ExploreViewTestCase):

    def test_unfiltered_graph(self):
        data = self.client.get(self.graph_url()).json()

        self.assertTrue(data["success"])
        self.assertEqual(len(data["payload"]["nodes"]), 3)
        self.assertEqual(len(data["payload"]["edges"]), 1)
        self.assertEqual(data["summary"]["shownObjects"], 3)
        self.assertEqual(data["state"]["hiddenObjectTypes"], [])
        self.assertEqual(data["canvasBackground"], "#FFFFFF")

    def test_hiding_an_object_type_hides_its_objects_and_dependent_relationships(self):
        data = self.client.get(self.graph_url(hide_objects=str(self.team_type.id))).json()

        self.assertEqual({n["label"] for n in data["payload"]["nodes"]}, {"Alice"})
        self.assertEqual(data["payload"]["edges"], [])
        self.assertEqual(data["summary"]["hiddenByObjectType"], 1)

    def test_hiding_a_relationship_type_keeps_its_endpoints(self):
        data = self.client.get(self.graph_url(hide_relationships=str(self.member_of.id))).json()

        self.assertEqual(len(data["payload"]["nodes"]), 3)
        self.assertEqual(data["payload"]["edges"], [])

    def test_attribute_filter(self):
        filters = json.dumps([{"type_id": str(self.person_type.id), "key": "status", "value": ["Active"]}])

        data = self.client.get(self.graph_url(filters=filters)).json()

        labels = sorted(n["label"] for n in data["payload"]["nodes"])
        self.assertEqual(labels, ["Alice", "Ops"])  # one Alice, and the untouched Team
        self.assertEqual(data["summary"]["hiddenByAttributeFilter"], 1)

    def test_zero_result_filter_gives_an_empty_valid_graph(self):
        filters = json.dumps([{"type_id": str(self.person_type.id), "key": "status", "value": ["Nope"]}])

        data = self.client.get(
            self.graph_url(filters=filters, hide_objects=str(self.team_type.id))
        ).json()

        self.assertTrue(data["success"])
        self.assertEqual(data["payload"]["nodes"], [])
        self.assertEqual(data["summary"]["shownObjects"], 0)
        self.assertEqual(data["summary"]["totalObjects"], 3)

    def test_include_brings_a_hidden_object_back(self):
        data = self.client.get(
            self.graph_url(hide_objects=str(self.team_type.id), include=str(self.ops.id))
        ).json()

        self.assertIn(str(self.ops.id), self.node_ids_from(data))
        self.assertEqual(len(data["payload"]["edges"]), 1)

    def node_ids_from(self, data):
        return {n["id"] for n in data["payload"]["nodes"]}

    def test_stale_ids_are_dropped_and_reported_and_the_echo_is_clean(self):
        stale = str(uuid.uuid4())

        data = self.client.get(
            self.graph_url(hide_objects=[stale, str(self.team_type.id)], include="not-a-uuid")
        ).json()

        self.assertTrue(data["success"])
        self.assertEqual(data["state"]["hiddenObjectTypes"], [str(self.team_type.id)])
        self.assertEqual(data["state"]["include"], [])
        self.assertEqual({d["kind"] for d in data["dropped"]}, {"object_type", "object"})

    def test_malformed_filters_are_a_400_not_a_crash(self):
        response = self.client.get(self.graph_url(filters="{not json"))

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["success"])

    def test_invalid_filter_entries_are_dropped(self):
        filters = json.dumps([{"type_id": str(uuid.uuid4()), "key": "x", "value": ["y"]}])

        data = self.client.get(self.graph_url(filters=filters)).json()

        self.assertEqual(data["state"]["attributeFilters"], [])
        self.assertEqual(data["dropped"][0]["kind"], "attribute_filter")

    def test_the_payload_is_size_bounded(self):
        for n in range(15):
            self.make_object(self.person_type, f"Extra {n:02d}")

        data = self.client.get(self.graph_url(limit=10)).json()

        self.assertEqual(len(data["payload"]["nodes"]), 10)
        self.assertTrue(data["summary"]["truncated"])
        self.assertEqual(data["summary"]["matchingObjects"], 18)

    def test_appearance_matches_the_service(self):
        AppearanceService.set_type_style(self.model, OBJECT_TYPE, self.person_type.id, "shape", "star")
        AppearanceService.set_type_style(self.model, OBJECT_TYPE, self.person_type.id, "background", "#1c7ed6")

        data = self.client.get(self.graph_url()).json()

        styles = {n["label"]: n["style"] for n in data["payload"]["nodes"]}
        self.assertEqual((styles["Alice"]["shape"], styles["Alice"]["background"]), ("star", "#1C7ED6"))
        self.assertEqual(styles["Ops"]["shape"], "box")

    def test_edge_direction_is_subject_to_object(self):
        edge = self.client.get(self.graph_url()).json()["payload"]["edges"][0]

        self.assertEqual((edge["source"], edge["target"]), (str(self.alice.id), str(self.ops.id)))

    def test_proposed_changes_reach_the_graph_with_the_amber_treatment(self):
        proposal = self.working_proposal()
        draft_id = self.propose_object(proposal, self.person_type.id, "Draft")
        relationship_id = self.propose_relationship(proposal, draft_id, self.ops.id)
        activate_proposal(self.client, self.model.id, proposal)

        payload = self.client.get(self.graph_url()).json()["payload"]

        draft = next(n for n in payload["nodes"] if n["id"] == str(draft_id))
        self.assertEqual(draft["style"]["border"], AMBER)
        self.assertTrue(draft["data"]["is_proposed"])
        canonical = next(n for n in payload["nodes"] if n["id"] == str(self.ops.id))
        self.assertEqual(canonical["style"]["border"], "#4C6EF5")
        edge = next(e for e in payload["edges"] if e["id"] == str(relationship_id))
        self.assertEqual((edge["style"]["colour"], edge["style"]["dashes"]), (AMBER, True))

    def test_proposed_deactivation_removes_the_object_from_the_graph(self):
        proposal = self.working_proposal()
        self.update(proposal, "Object", self.alice.id, "is_active", False)
        activate_proposal(self.client, self.model.id, proposal)

        data = self.client.get(self.graph_url()).json()

        self.assertNotIn(str(self.alice.id), self.node_ids_from(data))
        self.assertEqual(data["payload"]["edges"], [])


class SearchEndpointTests(ExploreViewTestCase):

    def test_case_insensitive_partial_match_with_type(self):
        data = self.client.get(self.search_url("OP")).json()

        self.assertTrue(data["success"])
        self.assertEqual([(r["name"], r["typeName"]) for r in data["results"]], [("Ops", "Team")])

    def test_duplicate_names_are_returned_separately(self):
        data = self.client.get(self.search_url("alice")).json()

        self.assertEqual(data["total"], 2)
        self.assertEqual(len({r["id"] for r in data["results"]}), 2)
        # The status attribute distinguishes the two.
        self.assertEqual({r["subtitle"] for r in data["results"]}, {"Status: Active", "Status: Left"})

    def test_matches_attribute_values(self):
        data = self.client.get(self.search_url("left")).json()

        self.assertEqual([r["id"] for r in data["results"]], [str(self.alice_two.id)])
        self.assertEqual(data["results"][0]["match"]["field"], "Status")

    def test_no_results(self):
        data = self.client.get(self.search_url("zzzz")).json()

        self.assertEqual((data["total"], data["results"], data["truncated"]), (0, [], False))

    def test_empty_query(self):
        data = self.client.get(self.search_url("   ")).json()

        self.assertEqual((data["total"], data["results"]), (0, []))

    def test_results_are_capped_but_the_total_is_reported(self):
        for n in range(40):
            self.make_object(self.person_type, f"Bulk {n:02d}")

        data = self.client.get(self.search_url("bulk")).json()

        self.assertEqual(len(data["results"]), 25)
        self.assertEqual(data["total"], 40)
        self.assertTrue(data["truncated"])

    def test_results_outside_the_current_filter_are_found_and_flagged(self):
        data = self.client.get(self.search_url("ops", hide_objects=str(self.team_type.id))).json()

        self.assertEqual(data["total"], 1)
        self.assertIs(data["results"][0]["inView"], False)

    def test_results_in_view_are_flagged(self):
        self.assertIs(self.client.get(self.search_url("ops")).json()["results"][0]["inView"], True)

    def test_search_covers_proposed_objects_only_with_the_active_proposal(self):
        proposal = self.working_proposal()
        self.propose_object(proposal, self.team_type.id, "Zebra Team")

        self.assertEqual(self.client.get(self.search_url("zebra")).json()["total"], 0)

        activate_proposal(self.client, self.model.id, proposal)
        data = self.client.get(self.search_url("zebra")).json()
        self.assertEqual(data["total"], 1)
        self.assertTrue(data["results"][0]["isProposed"])

    def test_bad_filters_are_rejected(self):
        self.assertEqual(self.client.get(self.search_url("a", filters="nope")).status_code, 400)


class DetailsEndpointTests(ExploreViewTestCase):

    def test_object_details(self):
        data = self.client.get(self.object_url(self.ops.id)).json()

        details = data["details"]
        self.assertTrue(data["success"])
        self.assertEqual((details["name"], details["type"]["name"]), ("Ops", "Team"))
        (group,) = details["relationships"]
        self.assertEqual(group["type"]["name"], "Member of")
        (item,) = group["items"]
        self.assertEqual(item["direction"], "incoming")
        self.assertEqual(item["counterpart"]["id"], str(self.alice.id))

    def test_object_details_list_attributes_including_unset_ones(self):
        details = self.client.get(self.object_url(self.alice.id)).json()["details"]

        self.assertEqual([(a["key"], a["display"]) for a in details["attributes"]], [("status", "Active")])

    def test_relationship_details(self):
        details = self.client.get(self.relationship_url(self.membership.id)).json()["details"]

        self.assertEqual(details["kind"], "relationship")
        self.assertEqual(details["type"]["name"], "Member of")
        self.assertEqual((details["source"]["name"], details["target"]["name"]), ("Alice", "Ops"))
        self.assertEqual(details["cardinality"]["subject"], {"minimum": 0, "maximum": None})

    def test_unknown_ids_are_a_clear_404(self):
        for url in (self.object_url(uuid.uuid4()), self.relationship_url(uuid.uuid4())):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 404, url)
            body = response.json()
            self.assertFalse(body["success"])
            self.assertEqual(body["code"], "not_found")
            self.assertIn("no longer part of the effective model", body["error"])

    def test_an_object_id_is_not_a_relationship_id(self):
        self.assertEqual(self.client.get(self.relationship_url(self.alice.id)).status_code, 404)
        self.assertEqual(self.client.get(self.object_url(self.membership.id)).status_code, 404)

    def test_inactive_objects_are_not_reachable(self):
        ghost = self.make_object(self.person_type, "Ghost", is_active=False)

        self.assertEqual(self.client.get(self.object_url(ghost.id)).status_code, 404)

    def test_hidden_connections_and_visibility_reflect_the_filters(self):
        data = self.client.get(self.object_url(self.alice.id, hide_objects=str(self.team_type.id))).json()

        details = data["details"]
        self.assertTrue(details["inView"])
        self.assertEqual(details["hiddenConnectionIds"], [str(self.ops.id)])
        self.assertIs(details["relationships"][0]["items"][0]["counterpart"]["inView"], False)

    def test_an_object_hidden_by_filters_is_still_inspectable_and_flagged(self):
        response = self.client.get(self.object_url(self.ops.id, hide_objects=str(self.team_type.id)))

        self.assertEqual(response.status_code, 200)
        self.assertIs(response.json()["details"]["inView"], False)

    def test_proposed_deactivation_makes_the_selected_object_unavailable(self):
        self.assertEqual(self.client.get(self.object_url(self.alice.id)).status_code, 200)

        proposal = self.working_proposal()
        self.update(proposal, "Object", self.alice.id, "is_active", False)
        activate_proposal(self.client, self.model.id, proposal)

        self.assertEqual(self.client.get(self.object_url(self.alice.id)).status_code, 404)
        self.assertEqual(self.client.get(self.relationship_url(self.membership.id)).status_code, 404)

    def test_proposed_delete_makes_the_relationship_unavailable(self):
        proposal = self.working_proposal()
        self.add_change(
            proposal,
            operation=ProposalChange.Operation.DELETE,
            target_type="Relationship",
            target_id=self.membership.id,
        )
        activate_proposal(self.client, self.model.id, proposal)

        self.assertEqual(self.client.get(self.relationship_url(self.membership.id)).status_code, 404)
        self.assertEqual(self.client.get(self.object_url(self.alice.id)).status_code, 200)

    def test_proposed_updates_show_in_details(self):
        proposal = self.working_proposal()
        self.update(proposal, "Object", self.alice.id, "name", "Alicia")
        self.update(proposal, "Object", self.alice.id, "attributes.status", "Left")
        activate_proposal(self.client, self.model.id, proposal)

        details = self.client.get(self.object_url(self.alice.id)).json()["details"]

        self.assertEqual(details["name"], "Alicia")
        self.assertTrue(details["isProposed"])
        self.assertEqual(details["attributes"][0]["display"], "Left")
        # The relationship's counterpart sees the new name too.
        ops = self.client.get(self.object_url(self.ops.id)).json()["details"]
        self.assertEqual(ops["relationships"][0]["items"][0]["counterpart"]["name"], "Alicia")

    def test_proposed_relationship_between_canonical_and_proposed_objects(self):
        proposal = self.working_proposal()
        draft_id = self.propose_object(proposal, self.team_type.id, "Draft Team")
        relationship_id = self.propose_relationship(proposal, self.alice.id, draft_id)
        activate_proposal(self.client, self.model.id, proposal)

        details = self.client.get(self.relationship_url(relationship_id)).json()["details"]

        self.assertTrue(details["isProposed"])
        self.assertEqual((details["source"]["name"], details["target"]["name"]), ("Alice", "Draft Team"))

    def test_object_with_many_relationships(self):
        for n in range(60):
            self.make_relationship(self.make_object(self.person_type, f"P{n}"), self.ops)

        details = self.client.get(self.object_url(self.ops.id)).json()["details"]

        self.assertEqual(details["connectionCount"], 61)
        self.assertEqual(len(details["relationships"][0]["items"]), 61)


class ProvenanceTests(ExploreViewTestCase):
    """The details response carries a provenance chain derived from committed proposals."""

    def commit(self, revision, *, user=None, title="", note=""):
        proposal = Proposal.objects.create(
            model=self.model,
            created_by=user or self.user,
            status=Proposal.Status.COMPLETED,
            title=title,
            summary=note,
        )
        ProposalSubmissionResult.objects.create(
            proposal=proposal,
            outcome=ProposalSubmissionResult.Outcome.SUCCESS,
            before_revision=revision - 1,
            after_revision=revision,
        )
        return proposal

    def rename(self, proposal, target_type, target_id, before, after):
        return self.add_change(
            proposal,
            operation=ProposalChange.Operation.UPDATE,
            target_type=target_type,
            target_id=target_id,
            before={"field": "name", "value": before},
            after={"field": "name", "value": after},
        )

    def test_an_object_with_no_history_has_an_empty_chain(self):
        details = self.client.get(self.object_url(self.alice.id)).json()["details"]

        self.assertEqual(details["provenance"], {"entries": [], "truncated": False})

    def test_object_details_include_the_chain_with_evidence(self):
        proposal = self.commit(2, title="Rename Alice", note="HR confirmed")
        change = self.rename(proposal, "Object", self.alice.id, "Alice", "Alicia")
        EvidenceReference.objects.create(change=change, source="HR system", locator="rec 12", note="ok")

        details = self.client.get(self.object_url(self.alice.id)).json()["details"]

        (entry,) = details["provenance"]["entries"]
        self.assertEqual(entry["revision"], {"before": 1, "after": 2})
        self.assertEqual(entry["title"], "Rename Alice")
        self.assertEqual(entry["changeNote"], "HR confirmed")
        self.assertEqual(entry["proposer"], "user@example.com")
        self.assertEqual(entry["changes"][0]["summary"], "Renamed")
        self.assertEqual(
            entry["changes"][0]["evidence"],
            [{"source": "HR system", "locator": "rec 12", "note": "ok"}],
        )

    def test_relationship_details_include_the_chain(self):
        proposal = self.commit(2)
        self.add_change(
            proposal,
            operation=ProposalChange.Operation.CREATE,
            target_type="Relationship",
            target_id=self.membership.id,
            after={"subject_id": str(self.alice.id), "object_id": str(self.ops.id), "is_active": True, "attributes": {}},
        )

        details = self.client.get(self.relationship_url(self.membership.id)).json()["details"]

        (entry,) = details["provenance"]["entries"]
        self.assertEqual(entry["changes"][0]["after"], "Alice → Ops")

    def test_attribute_labels_come_from_the_selected_records_definitions(self):
        proposal = self.commit(2)
        self.add_change(
            proposal,
            operation=ProposalChange.Operation.UPDATE,
            target_type="Object",
            target_id=self.alice.id,
            before={"field": "attributes.status", "value": "Active"},
            after={"field": "attributes.status", "value": "Left"},
        )

        details = self.client.get(self.object_url(self.alice.id)).json()["details"]

        self.assertEqual(details["provenance"]["entries"][0]["changes"][0]["summary"], "Changed Status")

    def test_a_workspace_colleagues_committed_proposal_appears(self):
        colleague = CustomUser.objects.create_user(email="colleague@example.com", password="test-password")
        WorkspaceMember.objects.create(workspace=self.workspace, user=colleague, role=WorkspaceMember.Role.EDITOR)
        self.rename(self.commit(2, user=colleague), "Object", self.alice.id, "Alice", "Alicia")

        details = self.client.get(self.object_url(self.alice.id)).json()["details"]

        self.assertEqual(details["provenance"]["entries"][0]["proposer"], "colleague@example.com")

    def test_uncommitted_proposals_are_not_part_of_the_chain_even_when_active(self):
        proposal = self.working_proposal()
        change = self.update(proposal, "Object", self.alice.id, "name", "Alicia")
        EvidenceReference.objects.create(change=change, source="Draft evidence")
        activate_proposal(self.client, self.model.id, proposal)

        details = self.client.get(self.object_url(self.alice.id)).json()["details"]

        self.assertTrue(details["isProposed"])
        self.assertEqual(details["provenance"]["entries"], [])

    def test_the_chain_is_oldest_first(self):
        self.rename(self.commit(5), "Object", self.alice.id, "B", "C")
        self.rename(self.commit(3), "Object", self.alice.id, "A", "B")

        details = self.client.get(self.object_url(self.alice.id)).json()["details"]

        self.assertEqual([e["revision"]["after"] for e in details["provenance"]["entries"]], [3, 5])

    def test_the_payload_exposes_no_proposal_identity_or_navigation(self):
        proposal = self.commit(2)
        self.rename(proposal, "Object", self.alice.id, "A", "B")

        body = self.client.get(self.object_url(self.alice.id)).content.decode()

        self.assertNotIn(str(proposal.id), body)
        self.assertNotIn("/proposals/", body)

    def test_the_page_bootstrap_carries_no_provenance(self):
        self.rename(self.commit(2), "Object", self.alice.id, "A", "B")

        response = self.client.get(self.page_url())

        self.assertNotIn("provenance", response.context["explorer_bootstrap"])
        self.assertNotContains(response, "provenance")

    def test_reading_provenance_writes_nothing(self):
        change = self.rename(self.commit(2), "Object", self.alice.id, "A", "B")
        EvidenceReference.objects.create(change=change, source="Doc")
        before = ReadOnlyGuaranteeTests.snapshot(self)

        self.client.get(self.object_url(self.alice.id))
        self.client.get(self.relationship_url(self.membership.id))

        self.assertEqual(ReadOnlyGuaranteeTests.snapshot(self), before)

