import uuid

from django.test import TestCase
from django.urls import reverse

from account.models import CustomUser
from model.models.model import Model
from model.models.object_type import ObjectType
from model.models.proposal import Proposal, ProposalChange
from model.models.relationship_type import RelationshipType
from model.services.appearance import OBJECT_TYPE, RELATIONSHIP_TYPE, AppearanceService
from model.services.proposal.proposal import ProposalService
from model.views.tests.proposal_test_utils import activate_proposal
from workspace.models import Workspace, WorkspaceMember


class AppearanceViewTestCase(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.workspace = Workspace.objects.create(name="Test Workspace")
        cls.user = CustomUser.objects.create_user(email="user@example.com", password="test-password")
        WorkspaceMember.objects.create(workspace=cls.workspace, user=cls.user, role=WorkspaceMember.Role.OWNER)

        cls.model = Model.objects.create(workspace=cls.workspace, name="Test Model", revision=1)
        cls.object_type = ObjectType.objects.create(
            model=cls.model, name="Process", key="process", is_active=True
        )
        cls.relationship_type = RelationshipType.objects.create(
            model=cls.model, name="Contains", key="contains", is_active=True
        )

        cls.other_workspace = Workspace.objects.create(name="Other Workspace")
        cls.other_user = CustomUser.objects.create_user(email="other@example.com", password="test-password")
        WorkspaceMember.objects.create(
            workspace=cls.other_workspace, user=cls.other_user, role=WorkspaceMember.Role.OWNER
        )

    def setUp(self):
        self.client.force_login(self.user)

    def fresh_model(self):
        return Model.objects.get(pk=self.model.pk)

    def object_type_url(self, type_id=None):
        return reverse("model:object_type_appearance", args=[self.model.id, type_id or self.object_type.id])

    def relationship_type_url(self, type_id=None):
        return reverse(
            "model:relationship_type_appearance", args=[self.model.id, type_id or self.relationship_type.id]
        )

    def customise_url(self):
        return reverse("model:customise", args=[self.model.id])

    def field_map(self, form):
        return {field["key"]: field for group in form["groups"] for field in group["fields"]}

    def propose_type(self, target_type, key):
        proposal = ProposalService.get_or_create_working(self.model, self.user)
        type_id = uuid.uuid4()
        ProposalService.record_change(
            proposal=proposal,
            operation=ProposalChange.Operation.CREATE,
            target_type=target_type,
            target_id=type_id,
            parent_type="Model",
            parent_id=self.model.id,
            before=None,
            after={"name": key.title(), "key": key, "description": "", "sort_order": 0, "is_active": True},
        )
        return proposal, type_id


class TypeAppearanceEndpointTests(AppearanceViewTestCase):

    def test_saves_a_field_directly_and_returns_the_new_state(self):
        response = self.client.post(self.object_type_url(), {"field": "shape", "value": "square"})

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        fields = self.field_map(data["form"])
        self.assertEqual(fields["shape"]["value"], "square")
        self.assertTrue(fields["shape"]["overridden"])
        self.assertEqual(
            AppearanceService.resolve_object_type(self.fresh_model(), self.object_type.id).shape, "square"
        )

    def test_saving_is_not_a_proposal_operation(self):
        self.client.post(self.object_type_url(), {"field": "background", "value": "#ff00ff"})
        self.client.post(self.relationship_type_url(), {"field": "width", "value": "4"})

        self.assertFalse(Proposal.objects.exists())
        self.assertFalse(ProposalChange.objects.exists())
        self.assertEqual(self.fresh_model().revision, 1)

    def test_invalid_values_are_rejected_without_saving(self):
        for field, value in (("shape", "blob"), ("background", "red"), ("border_width", "99"), ("nope", "x")):
            response = self.client.post(self.object_type_url(), {"field": field, "value": value})

            self.assertEqual(response.status_code, 400, field)
            self.assertFalse(response.json()["success"])
            self.assertTrue(response.json()["error"])

        self.assertFalse(AppearanceService.has_type_style(self.fresh_model(), OBJECT_TYPE, self.object_type.id))

    def test_reset_field_and_reset_all(self):
        self.client.post(self.object_type_url(), {"field": "shape", "value": "square"})
        self.client.post(self.object_type_url(), {"field": "size", "value": "40"})

        response = self.client.post(self.object_type_url(), {"action": "reset_field", "field": "shape"})
        fields = self.field_map(response.json()["form"])
        self.assertFalse(fields["shape"]["overridden"])
        self.assertTrue(fields["size"]["overridden"])

        response = self.client.post(self.object_type_url(), {"action": "reset_all"})
        self.assertTrue(response.json()["success"])
        self.assertFalse(response.json()["form"]["has_overrides"])
        self.assertFalse(AppearanceService.has_type_style(self.fresh_model(), OBJECT_TYPE, self.object_type.id))

    def test_empty_value_clears_the_field(self):
        self.client.post(self.object_type_url(), {"field": "icon", "value": "person"})
        response = self.client.post(self.object_type_url(), {"field": "icon", "value": ""})

        self.assertTrue(response.json()["success"])
        self.assertIsNone(AppearanceService.resolve_object_type(self.fresh_model(), self.object_type.id).icon)

    def test_missing_field_and_unknown_action_are_bad_requests(self):
        self.assertEqual(self.client.post(self.object_type_url(), {"value": "x"}).status_code, 400)
        self.assertEqual(self.client.post(self.object_type_url(), {"action": "explode"}).status_code, 400)
        self.assertEqual(self.client.post(self.object_type_url(), {"action": "reset_field"}).status_code, 400)

    def test_unknown_type_is_404(self):
        response = self.client.post(self.object_type_url(uuid.uuid4()), {"field": "shape", "value": "square"})
        self.assertEqual(response.status_code, 404)
        self.assertFalse(response.json()["success"])

    def test_object_and_relationship_endpoints_are_kind_specific(self):
        # An object type id posted to the relationship endpoint is not a relationship type.
        response = self.client.post(self.relationship_type_url(self.object_type.id), {"field": "width", "value": "3"})
        self.assertEqual(response.status_code, 404)

    def test_get_is_not_allowed(self):
        self.assertEqual(self.client.get(self.object_type_url()).status_code, 405)

    def test_anonymous_users_cannot_save(self):
        self.client.logout()
        response = self.client.post(self.object_type_url(), {"field": "shape", "value": "square"})

        self.assertNotEqual(response.status_code, 200)
        self.assertFalse(AppearanceService.has_type_style(self.fresh_model(), OBJECT_TYPE, self.object_type.id))

    def test_users_of_other_workspaces_get_404(self):
        self.client.force_login(self.other_user)
        response = self.client.post(self.object_type_url(), {"field": "shape", "value": "square"})

        self.assertEqual(response.status_code, 404)
        self.assertFalse(AppearanceService.has_type_style(self.fresh_model(), OBJECT_TYPE, self.object_type.id))

    def test_relationship_type_fields_save(self):
        response = self.client.post(self.relationship_type_url(), {"field": "line_style", "value": "dotted"})
        self.assertTrue(response.json()["success"])
        self.client.post(self.relationship_type_url(), {"field": "arrows", "value": "both"})

        resolved = AppearanceService.resolve_relationship_type(self.fresh_model(), self.relationship_type.id)
        self.assertEqual((resolved.line_style, resolved.arrows), ("dotted", "both"))

    def test_proposed_only_types_can_be_styled_directly(self):
        _proposal, type_id = self.propose_type("ObjectType", "draft")
        _proposal, relationship_id = self.propose_type("RelationshipType", "links")

        response = self.client.post(self.object_type_url(type_id), {"field": "shape", "value": "star"})
        self.assertEqual(response.status_code, 200)
        response = self.client.post(self.relationship_type_url(relationship_id), {"field": "width", "value": "4"})
        self.assertEqual(response.status_code, 200)

        model = self.fresh_model()
        self.assertEqual(AppearanceService.resolve_object_type(model, type_id).shape, "star")
        self.assertTrue(AppearanceService.has_type_style(model, RELATIONSHIP_TYPE, relationship_id))
        # Only the two CREATEs; styling added no changes.
        self.assertEqual(ProposalChange.objects.count(), 2)


class EditorRenderingTests(AppearanceViewTestCase):

    def object_editor(self, type_id=None):
        return self.client.get(reverse("model:object_type_edit", args=[self.model.id, type_id or self.object_type.id]))

    def relationship_editor(self, type_id=None):
        return self.client.get(
            reverse("model:relationship_type_edit", args=[self.model.id, type_id or self.relationship_type.id])
        )

    def test_object_type_editor_shows_the_appearance_section(self):
        response = self.object_editor()

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<h2>Appearance</h2>", html=True)
        self.assertContains(response, self.object_type_url())
        self.assertContains(response, "data-appearance-form")
        self.assertIn("appearance_form", response.context)
        self.assertEqual(response.context["appearance_form"]["kind"], "object_type")

    def test_relationship_type_editor_shows_the_appearance_section(self):
        response = self.relationship_editor()

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<h2>Appearance</h2>", html=True)
        self.assertContains(response, self.relationship_type_url())
        self.assertEqual(response.context["appearance_form"]["kind"], "relationship_type")

    def test_editor_loads_saved_values(self):
        AppearanceService.set_type_style(self.model, OBJECT_TYPE, self.object_type.id, "shape", "square")
        AppearanceService.set_type_style(self.model, OBJECT_TYPE, self.object_type.id, "background", "#ff00ff")
        AppearanceService.set_type_style(self.model, RELATIONSHIP_TYPE, self.relationship_type.id, "line_style", "dotted")

        object_fields = self.field_map(self.object_editor().context["appearance_form"])
        self.assertEqual(object_fields["shape"]["value"], "square")
        self.assertEqual(object_fields["background"]["value"], "#FF00FF")
        self.assertTrue(object_fields["shape"]["overridden"])
        self.assertContains(self.object_editor(), '<option value="square" selected>Square</option>', html=True)

        relationship_fields = self.field_map(self.relationship_editor().context["appearance_form"])
        self.assertEqual(relationship_fields["line_style"]["value"], "dotted")

    def test_editor_shows_inherited_values_from_model_customisation(self):
        AppearanceService.update_customisation(self.model, "object", "shape", "ellipse")

        fields = self.field_map(self.object_editor().context["appearance_form"])
        self.assertEqual(fields["shape"]["value"], "ellipse")
        self.assertFalse(fields["shape"]["overridden"])

    def test_save_then_reload_round_trips(self):
        self.client.post(self.object_type_url(), {"field": "font_weight", "value": "bold"})

        fields = self.field_map(self.object_editor().context["appearance_form"])
        self.assertEqual(fields["font_weight"]["value"], "bold")

    def test_create_page_has_no_appearance_section(self):
        response = self.client.get(reverse("model:object_type_create", args=[self.model.id]))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "data-appearance-form")

    def test_proposed_only_type_editor_shows_appearance(self):
        proposal, type_id = self.propose_type("ObjectType", "draft")
        activate_proposal(self.client, self.model.id, proposal)

        response = self.object_editor(type_id)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-appearance-form")
        self.assertEqual(response.context["appearance_form"]["type_id"], str(type_id))

    def test_editors_still_post_properties_through_the_proposal_system(self):
        response = self.client.post(
            reverse("model:object_type_edit", args=[self.model.id, self.object_type.id]),
            {"field": "description", "value": "Updated"},
        )

        self.assertTrue(response.json()["success"])
        self.assertTrue(ProposalChange.objects.filter(target_type="ObjectType", after__field="description").exists())
        self.object_type.refresh_from_db()
        self.assertEqual(self.object_type.description, "")


class CustomisePageTests(AppearanceViewTestCase):

    def test_get_renders_the_page_with_all_scopes(self):
        response = self.client.get(self.customise_url())

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "model/customise.html")
        scopes = [scope["scope"] for scope in response.context["appearance_form"]["scopes"]]
        self.assertEqual(scopes, ["theme", "object", "relationship"])
        self.assertContains(response, "Reset all to Weave defaults")
        self.assertEqual(response.context["canvas_background"], "#FFFFFF")

    def test_sidebar_lists_customise_under_understand_and_marks_it_active(self):
        response = self.client.get(self.customise_url())
        html = response.content.decode()

        self.assertIn(f'href="{self.customise_url()}"', html)
        understand = html[html.index("Understand") : html.index("Define")]
        self.assertLess(understand.index("Assets"), understand.index("Customise"))
        self.assertRegex(understand, r'model-nav-item\s+active\s+"\s*>\s*<span>Customise</span>')
        self.assertIn('aria-expanded="true"', understand)

    def test_sidebar_link_is_present_on_other_model_pages(self):
        response = self.client.get(reverse("model:overview", args=[self.model.id]))
        self.assertContains(response, f'href="{self.customise_url()}"')

    def test_preview_payload_reflects_the_saved_customisation(self):
        AppearanceService.update_customisation(self.model, "object", "shape", "ellipse")
        response = self.client.get(self.customise_url())

        payload = response.context["ontology_payload"]
        self.assertEqual(payload["nodes"][0]["style"]["shape"], "ellipse")
        self.assertTrue(response.context["has_types"])

    def test_post_saves_directly_and_returns_fresh_preview(self):
        response = self.client.post(
            self.customise_url(), {"scope": "theme", "field": "accent", "value": "#00aa00"}
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["payload"]["nodes"][0]["style"]["border"], "#00AA00")
        self.assertEqual(data["canvas_background"], "#FFFFFF")
        self.assertTrue(data["form"]["has_customisation"])
        self.assertEqual(AppearanceService.resolve_theme(self.fresh_model()).accent, "#00AA00")

    def test_canvas_background_is_returned_for_the_page_to_apply(self):
        data = self.client.post(
            self.customise_url(), {"scope": "theme", "field": "canvas_background", "value": "#101010"}
        ).json()

        self.assertEqual(data["canvas_background"], "#101010")
        self.assertEqual(data["payload"]["viewer_config"]["extra"]["canvas_background"], "#101010")

    def test_font_family_change_reaches_the_preview_labels(self):
        stack = "Georgia, 'Times New Roman', serif"
        data = self.client.post(
            self.customise_url(), {"scope": "theme", "field": "font_family", "value": stack}
        ).json()

        self.assertTrue(data["success"])
        self.assertEqual(data["payload"]["nodes"][0]["style"]["font"]["face"], stack)

    def test_arbitrary_font_family_is_rejected(self):
        response = self.client.post(
            self.customise_url(), {"scope": "theme", "field": "font_family", "value": "Comic Sans MS"}
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["success"])

    def test_invalid_scope_field_and_value_are_rejected(self):
        for data in (
            {"scope": "bogus", "field": "shape", "value": "box"},
            {"scope": "object", "field": "icon", "value": "person"},
            {"scope": "object", "field": "shape", "value": "blob"},
            {"scope": "object", "value": "box"},
        ):
            self.assertEqual(self.client.post(self.customise_url(), data).status_code, 400, data)

    def test_reset_field_clears_one_model_setting(self):
        self.client.post(self.customise_url(), {"scope": "object", "field": "shape", "value": "ellipse"})
        self.client.post(self.customise_url(), {"scope": "object", "field": "background", "value": "#111111"})

        data = self.client.post(
            self.customise_url(), {"scope": "object", "action": "reset_field", "field": "shape"}
        ).json()

        self.assertTrue(data["success"])
        object_scope = next(scope for scope in data["form"]["scopes"] if scope["scope"] == "object")
        fields = {f["key"]: f for group in object_scope["groups"] for f in group["fields"]}
        self.assertFalse(fields["shape"]["overridden"])
        self.assertTrue(fields["background"]["overridden"])

    def test_reset_all_clears_model_customisation_but_keeps_type_overrides(self):
        AppearanceService.set_type_style(self.model, OBJECT_TYPE, self.object_type.id, "shape", "star")
        AppearanceService.set_type_style(self.model, RELATIONSHIP_TYPE, self.relationship_type.id, "width", 4)
        self.client.post(self.customise_url(), {"scope": "theme", "field": "accent", "value": "#00aa00"})
        self.client.post(self.customise_url(), {"scope": "object", "field": "shape", "value": "ellipse"})

        data = self.client.post(self.customise_url(), {"action": "reset_all"}).json()

        self.assertTrue(data["success"])
        self.assertFalse(data["form"]["has_customisation"])
        model = self.fresh_model()
        self.assertEqual(AppearanceService.resolve_theme(model).accent, "#4C6EF5")
        # Type overrides are independent and untouched.
        self.assertEqual(AppearanceService.resolve_object_type(model, self.object_type.id).shape, "star")
        self.assertEqual(AppearanceService.resolve_relationship_type(model, self.relationship_type.id).width, 4)
        self.assertEqual(data["payload"]["nodes"][0]["style"]["shape"], "star")

    def test_customise_is_not_governed_by_proposals(self):
        self.client.post(self.customise_url(), {"scope": "theme", "field": "accent", "value": "#00aa00"})

        self.assertFalse(Proposal.objects.exists())
        self.assertFalse(ProposalChange.objects.exists())
        self.assertEqual(self.fresh_model().revision, 1)

    def test_preview_includes_the_active_proposal_overlay(self):
        proposal, type_id = self.propose_type("ObjectType", "draft")
        activate_proposal(self.client, self.model.id, proposal)

        data = self.client.post(
            self.customise_url(), {"scope": "theme", "field": "accent", "value": "#00aa00"}
        ).json()

        nodes = {node["id"]: node for node in data["payload"]["nodes"]}
        self.assertEqual(nodes[str(type_id)]["style"]["border"], "#F08C00")
        self.assertEqual(nodes[str(self.object_type.id)]["style"]["border"], "#00AA00")

    def test_anonymous_and_foreign_users_are_refused(self):
        self.client.logout()
        self.assertNotEqual(self.client.get(self.customise_url()).status_code, 200)
        self.assertNotEqual(
            self.client.post(self.customise_url(), {"scope": "theme", "field": "accent", "value": "#00aa00"}).status_code,
            200,
        )

        self.client.force_login(self.other_user)
        self.assertEqual(self.client.get(self.customise_url()).status_code, 404)
        self.assertEqual(
            self.client.post(self.customise_url(), {"scope": "theme", "field": "accent", "value": "#00aa00"}).status_code,
            404,
        )
        self.assertFalse(AppearanceService.has_customisation(self.fresh_model()))

    def test_empty_model_shows_an_empty_state_hint(self):
        empty = Model.objects.create(workspace=self.workspace, name="Empty", revision=1)
        response = self.client.get(reverse("model:customise", args=[empty.id]))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["has_types"])
        self.assertContains(response, "no types yet")


class OverviewIntegrationTests(AppearanceViewTestCase):

    def test_overview_payload_uses_customised_styles(self):
        AppearanceService.update_customisation(self.model, "object", "background", "#123456")
        AppearanceService.set_type_style(self.model, OBJECT_TYPE, self.object_type.id, "shape", "star")
        response = self.client.get(reverse("model:overview", args=[self.model.id]))

        style = response.context["ontology_payload"]["nodes"][0]["style"]
        self.assertEqual((style["shape"], style["background"]), ("star", "#123456"))

    def test_overview_applies_canvas_background_and_legend_colours(self):
        AppearanceService.update_customisation(self.model, "theme", "canvas_background", "#101010")
        AppearanceService.update_customisation(self.model, "theme", "accent", "#00aa00")
        response = self.client.get(reverse("model:overview", args=[self.model.id]))

        self.assertContains(response, "background: #101010;")
        self.assertContains(response, "--legend-node-border: #00AA00;")
        self.assertContains(response, "--legend-proposed: #F08C00;")
