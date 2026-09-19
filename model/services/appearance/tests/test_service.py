import uuid

from django.test import TestCase

from account.models import CustomUser
from model.models.model import Model
from model.models.object_type import ObjectType
from model.models.proposal import Proposal, ProposalChange
from model.models.relationship_type import RelationshipType
from model.services.appearance import (
    OBJECT_TYPE,
    RELATIONSHIP_TYPE,
    AppearanceService,
    AppearanceValidationError,
    UnknownTypeError,
)
from model.services.proposal import submission
from model.services.proposal.proposal import ProposalService
from workspace.models import Workspace


def _drain(model_id):
    while True:
        proposal = submission.claim_next(model_id)
        if proposal is None:
            return
        submission.process(proposal.id)


class AppearanceServiceTestCase(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.workspace = Workspace.objects.create(name="Test Workspace")
        cls.user = CustomUser.objects.create_user(email="user@example.com", password="test-password")
        cls.model = Model.objects.create(workspace=cls.workspace, name="Test Model", revision=1)

    def make_object_type(self, key="process", model=None):
        return ObjectType.objects.create(model=model or self.model, name=key.title(), key=key, is_active=True)

    def make_relationship_type(self, key="contains", model=None):
        return RelationshipType.objects.create(model=model or self.model, name=key.title(), key=key, is_active=True)

    def propose_type(self, proposal, target_type, key, model=None):
        type_id = uuid.uuid4()
        ProposalService.record_change(
            proposal=proposal,
            operation=ProposalChange.Operation.CREATE,
            target_type=target_type,
            target_id=type_id,
            parent_type="Model",
            parent_id=(model or self.model).id,
            before=None,
            after={"name": key.title(), "key": key, "description": "", "sort_order": 0, "is_active": True},
        )
        return type_id

    def working_proposal(self, model=None):
        return ProposalService.get_or_create_working(model or self.model, self.user)

    def stored(self, model=None):
        """The raw persisted document (tests only: consumers never read this)."""
        return Model.objects.get(pk=(model or self.model).pk).appearance


class PersistenceAndDefaultsTests(AppearanceServiceTestCase):

    def test_new_model_resolves_to_built_in_defaults(self):
        object_type = self.make_object_type()
        resolver = AppearanceService.resolver(self.model)

        self.assertEqual(resolver.theme.accent, "#4C6EF5")
        self.assertEqual(resolver.theme.canvas_background, "#FFFFFF")
        appearance = resolver.object_type(object_type.id)
        self.assertEqual((appearance.shape, appearance.background, appearance.border), ("box", "#EDF2FF", "#4C6EF5"))
        self.assertFalse(AppearanceService.has_customisation(self.model))

    def test_customisation_persists_and_reloads_from_the_database(self):
        AppearanceService.update_customisation(self.model, "theme", "accent", "#ff0000")
        AppearanceService.update_customisation(self.model, "object", "shape", "ellipse")

        fresh = Model.objects.get(pk=self.model.pk)
        resolver = AppearanceService.resolver(fresh)
        self.assertEqual(resolver.theme.accent, "#FF0000")
        self.assertEqual(resolver.object_type(uuid.uuid4()).shape, "ellipse")
        self.assertTrue(AppearanceService.has_customisation(fresh))

    def test_saving_appearance_does_not_bump_revision(self):
        AppearanceService.update_customisation(self.model, "theme", "accent", "#ff0000")
        object_type = self.make_object_type()
        AppearanceService.set_type_style(self.model, OBJECT_TYPE, object_type.id, "shape", "star")

        self.assertEqual(Model.objects.get(pk=self.model.pk).revision, 1)

    def test_invalid_value_is_rejected_and_nothing_is_stored(self):
        before = self.stored()

        with self.assertRaises(AppearanceValidationError):
            AppearanceService.update_customisation(self.model, "theme", "font_family", "Comic Sans MS")
        with self.assertRaises(AppearanceValidationError):
            AppearanceService.update_customisation(self.model, "object", "shape", "blob")
        with self.assertRaises(AppearanceValidationError):
            AppearanceService.update_customisation(self.model, "nope", "shape", "box")
        with self.assertRaises(AppearanceValidationError):
            AppearanceService.update_customisation(self.model, "object", "icon", "person")  # type-level only

        self.assertEqual(self.stored(), before)

    def test_clearing_a_value_falls_back_to_the_built_in(self):
        AppearanceService.update_customisation(self.model, "theme", "accent", "#ff0000")
        AppearanceService.update_customisation(self.model, "theme", "accent", "")

        self.assertEqual(AppearanceService.resolve_theme(self.model).accent, "#4C6EF5")
        self.assertFalse(AppearanceService.has_customisation(self.model))

    def test_corrupt_stored_document_falls_back_to_defaults(self):
        Model.objects.filter(pk=self.model.pk).update(appearance={"theme": {"accent": "javascript:1"}, "objects": 5})
        fresh = Model.objects.get(pk=self.model.pk)

        self.assertEqual(AppearanceService.resolve_theme(fresh).accent, "#4C6EF5")

    def test_customisation_is_per_model(self):
        other = Model.objects.create(workspace=self.workspace, name="Other", revision=1)
        AppearanceService.update_customisation(self.model, "theme", "accent", "#ff0000")

        self.assertEqual(AppearanceService.resolve_theme(other).accent, "#4C6EF5")


class InheritanceTests(AppearanceServiceTestCase):

    def test_type_override_beats_model_customisation_beats_built_in(self):
        styled = self.make_object_type("styled")
        plain = self.make_object_type("plain")

        AppearanceService.update_customisation(self.model, "object", "shape", "ellipse")
        AppearanceService.update_customisation(self.model, "object", "background", "#111111")
        AppearanceService.set_type_style(self.model, OBJECT_TYPE, styled.id, "shape", "square")

        resolver = AppearanceService.resolver(self.model)
        self.assertEqual(resolver.object_type(styled.id).shape, "square")  # type override
        self.assertEqual(resolver.object_type(styled.id).background, "#111111")  # model
        self.assertEqual(resolver.object_type(plain.id).shape, "ellipse")  # model
        self.assertEqual(resolver.object_type(plain.id).border, "#4C6EF5")  # built-in

    def test_clearing_a_type_field_falls_back_one_layer(self):
        object_type = self.make_object_type()
        AppearanceService.update_customisation(self.model, "object", "shape", "ellipse")
        AppearanceService.set_type_style(self.model, OBJECT_TYPE, object_type.id, "shape", "square")
        AppearanceService.clear_type_style(self.model, OBJECT_TYPE, object_type.id, "shape")

        self.assertEqual(AppearanceService.resolve_object_type(self.model, object_type.id).shape, "ellipse")
        self.assertFalse(AppearanceService.has_type_style(self.model, OBJECT_TYPE, object_type.id))

    def test_accent_recolours_default_borders_but_not_overridden_ones(self):
        default_type = self.make_object_type("default")
        custom_type = self.make_object_type("custom")
        AppearanceService.set_type_style(self.model, OBJECT_TYPE, custom_type.id, "border", "#222222")
        AppearanceService.update_customisation(self.model, "theme", "accent", "#00aa00")

        resolver = AppearanceService.resolver(self.model)
        self.assertEqual(resolver.object_type(default_type.id).border, "#00AA00")
        self.assertEqual(resolver.object_type(custom_type.id).border, "#222222")

    def test_relationship_type_layering(self):
        relationship_type = self.make_relationship_type()
        AppearanceService.update_customisation(self.model, "relationship", "line_style", "dashed")
        AppearanceService.update_customisation(self.model, "relationship", "width", 3)
        AppearanceService.set_type_style(self.model, RELATIONSHIP_TYPE, relationship_type.id, "line_style", "dotted")

        resolved = AppearanceService.resolve_relationship_type(self.model, relationship_type.id)
        self.assertEqual(resolved.line_style, "dotted")
        self.assertEqual(resolved.width, 3)
        self.assertEqual(resolved.arrows, "to")

    def test_font_family_reaches_every_type_kind(self):
        stack = "Georgia, 'Times New Roman', serif"
        object_type = self.make_object_type()
        relationship_type = self.make_relationship_type()
        AppearanceService.update_customisation(self.model, "theme", "font_family", stack)

        self.assertEqual(AppearanceService.resolve_object_type(self.model, object_type.id).font_family, stack)
        self.assertEqual(
            AppearanceService.resolve_relationship_type(self.model, relationship_type.id).font_family, stack
        )

    def test_kinds_do_not_share_overrides_even_for_the_same_id(self):
        shared_id = uuid.uuid4()
        ObjectType.objects.create(id=shared_id, model=self.model, name="A", key="a")
        RelationshipType.objects.create(id=shared_id, model=self.model, name="B", key="b")
        AppearanceService.set_type_style(self.model, OBJECT_TYPE, shared_id, "shape", "star")

        self.assertEqual(AppearanceService.resolve_object_type(self.model, shared_id).shape, "star")
        self.assertEqual(AppearanceService.resolve_relationship_type(self.model, shared_id).line_style, "solid")


class TypeStyleTests(AppearanceServiceTestCase):

    def test_unknown_type_is_rejected(self):
        with self.assertRaises(UnknownTypeError):
            AppearanceService.set_type_style(self.model, OBJECT_TYPE, uuid.uuid4(), "shape", "star")
        with self.assertRaises(UnknownTypeError):
            AppearanceService.set_type_style(self.model, OBJECT_TYPE, "not-a-uuid", "shape", "star")

    def test_type_of_another_model_is_rejected(self):
        other = Model.objects.create(workspace=self.workspace, name="Other", revision=1)
        foreign = self.make_object_type("foreign", model=other)

        with self.assertRaises(UnknownTypeError):
            AppearanceService.set_type_style(self.model, OBJECT_TYPE, foreign.id, "shape", "star")

    def test_proposed_only_type_can_be_styled_immediately(self):
        proposal = self.working_proposal()
        type_id = self.propose_type(proposal, "ObjectType", "draft")

        AppearanceService.set_type_style(self.model, OBJECT_TYPE, type_id, "background", "#ff00ff")

        self.assertEqual(AppearanceService.resolve_object_type(self.model, type_id).background, "#FF00FF")

    def test_style_creates_no_proposal_changes(self):
        object_type = self.make_object_type()
        AppearanceService.set_type_style(self.model, OBJECT_TYPE, object_type.id, "shape", "star")
        AppearanceService.update_customisation(self.model, "theme", "accent", "#ff0000")

        self.assertFalse(ProposalChange.objects.exists())
        self.assertFalse(Proposal.objects.exists())

    def test_icon_is_valid_on_an_object_type(self):
        object_type = self.make_object_type()
        AppearanceService.set_type_style(self.model, OBJECT_TYPE, object_type.id, "icon", "database")

        self.assertEqual(AppearanceService.resolve_object_type(self.model, object_type.id).icon, "database")

    def test_clear_all_removes_the_type_entry(self):
        object_type = self.make_object_type()
        AppearanceService.set_type_style(self.model, OBJECT_TYPE, object_type.id, "shape", "star")
        AppearanceService.set_type_style(self.model, OBJECT_TYPE, object_type.id, "size", 40)
        AppearanceService.clear_type_style(self.model, OBJECT_TYPE, object_type.id)

        self.assertFalse(AppearanceService.has_type_style(self.model, OBJECT_TYPE, object_type.id))


class ResetScopeTests(AppearanceServiceTestCase):

    def test_reset_customisation_clears_model_layer_only(self):
        object_type = self.make_object_type()
        relationship_type = self.make_relationship_type()
        AppearanceService.set_type_style(self.model, OBJECT_TYPE, object_type.id, "shape", "star")
        AppearanceService.set_type_style(self.model, RELATIONSHIP_TYPE, relationship_type.id, "width", 4)
        AppearanceService.update_customisation(self.model, "theme", "accent", "#ff0000")
        AppearanceService.update_customisation(self.model, "object", "shape", "ellipse")
        AppearanceService.update_customisation(self.model, "relationship", "arrows", "none")
        type_entries_before = {
            key: self.stored()[key] for key in ("object_types", "relationship_types")
        }

        AppearanceService.reset_customisation(self.model)

        self.assertFalse(AppearanceService.has_customisation(self.model))
        self.assertEqual(AppearanceService.resolve_theme(self.model).accent, "#4C6EF5")
        self.assertEqual(
            {key: self.stored()[key] for key in ("object_types", "relationship_types")},
            type_entries_before,
        )
        self.assertEqual(AppearanceService.resolve_object_type(self.model, object_type.id).shape, "star")
        self.assertEqual(AppearanceService.resolve_relationship_type(self.model, relationship_type.id).width, 4)


class FormStructureTests(AppearanceServiceTestCase):

    def fields(self, form):
        return {
            field["key"]: field
            for group in form["groups"]
            for field in group["fields"]
        }

    def test_type_form_reports_value_inherited_value_and_override(self):
        object_type = self.make_object_type()
        AppearanceService.update_customisation(self.model, "object", "shape", "ellipse")
        AppearanceService.set_type_style(self.model, OBJECT_TYPE, object_type.id, "shape", "square")

        fields = self.fields(AppearanceService.type_form(self.model, OBJECT_TYPE, object_type.id))

        self.assertEqual(fields["shape"]["value"], "square")
        self.assertEqual(fields["shape"]["inherited"], "ellipse")
        self.assertTrue(fields["shape"]["overridden"])
        self.assertFalse(fields["background"]["overridden"])
        self.assertEqual(fields["background"]["value"], "#EDF2FF")
        self.assertEqual(fields["icon"]["value"], "")

    def test_customisation_form_has_three_scopes_and_no_type_only_fields(self):
        form = AppearanceService.customisation_form(self.model)

        self.assertEqual([scope["scope"] for scope in form["scopes"]], ["theme", "object", "relationship"])
        object_keys = {
            field["key"] for group in form["scopes"][1]["groups"] for field in group["fields"]
        }
        self.assertNotIn("icon", object_keys)
        self.assertIn("shape", object_keys)
        self.assertFalse(form["has_customisation"])

    def test_customisation_form_reflects_customisation_and_inherited_border(self):
        AppearanceService.update_customisation(self.model, "theme", "accent", "#00aa00")
        form = AppearanceService.customisation_form(self.model)

        self.assertTrue(form["has_customisation"])
        object_fields = {f["key"]: f for g in form["scopes"][1]["groups"] for f in g["fields"]}
        self.assertEqual(object_fields["border"]["value"], "#00AA00")
        self.assertEqual(object_fields["border"]["inherited"], "#00AA00")
        self.assertFalse(object_fields["border"]["overridden"])

    def test_font_family_field_offers_only_curated_stacks(self):
        form = AppearanceService.customisation_form(self.model)
        theme_fields = {f["key"]: f for g in form["scopes"][0]["groups"] for f in g["fields"]}

        offered = [choice["value"] for choice in theme_fields["font_family"]["choices"]]
        from model.services.appearance.schema import FONT_STACKS

        self.assertEqual(offered, [stack for stack, _label in FONT_STACKS])


class PruneLifecycleTests(AppearanceServiceTestCase):

    def test_abandoning_a_proposal_prunes_styles_of_its_proposed_types(self):
        proposal = self.working_proposal()
        proposed = self.propose_type(proposal, "ObjectType", "draft")
        proposed_rel = self.propose_type(proposal, "RelationshipType", "links")
        canonical = self.make_object_type()
        AppearanceService.set_type_style(self.model, OBJECT_TYPE, proposed, "shape", "star")
        AppearanceService.set_type_style(self.model, RELATIONSHIP_TYPE, proposed_rel, "width", 4)
        AppearanceService.set_type_style(self.model, OBJECT_TYPE, canonical.id, "shape", "square")

        ProposalService.abandon(proposal)

        self.assertFalse(AppearanceService.has_type_style(self.model, OBJECT_TYPE, proposed))
        self.assertFalse(AppearanceService.has_type_style(self.model, RELATIONSHIP_TYPE, proposed_rel))
        self.assertTrue(AppearanceService.has_type_style(self.model, OBJECT_TYPE, canonical.id))

    def test_discarding_a_proposed_type_prunes_only_its_style(self):
        proposal = self.working_proposal()
        discarded = self.propose_type(proposal, "ObjectType", "discarded")
        kept = self.propose_type(proposal, "ObjectType", "kept")
        AppearanceService.set_type_style(self.model, OBJECT_TYPE, discarded, "shape", "star")
        AppearanceService.set_type_style(self.model, OBJECT_TYPE, kept, "shape", "square")

        ProposalService.discard_change(proposal=proposal, target_type="ObjectType", target_id=discarded)

        self.assertFalse(AppearanceService.has_type_style(self.model, OBJECT_TYPE, discarded))
        self.assertTrue(AppearanceService.has_type_style(self.model, OBJECT_TYPE, kept))

    def test_discarding_an_unrelated_field_change_keeps_style(self):
        proposal = self.working_proposal()
        type_id = self.propose_type(proposal, "ObjectType", "draft")
        AppearanceService.set_type_style(self.model, OBJECT_TYPE, type_id, "shape", "star")

        ProposalService.discard_change(proposal=proposal, target_type="ObjectType", target_id=uuid.uuid4())

        self.assertTrue(AppearanceService.has_type_style(self.model, OBJECT_TYPE, type_id))

    def test_approval_keeps_the_style_on_the_now_canonical_type(self):
        proposal = self.working_proposal()
        type_id = self.propose_type(proposal, "ObjectType", "draft")
        AppearanceService.set_type_style(self.model, OBJECT_TYPE, type_id, "shape", "star")

        ProposalService.submit(proposal)
        _drain(self.model.id)

        self.assertTrue(ObjectType.objects.filter(id=type_id).exists())
        fresh = Model.objects.get(pk=self.model.pk)
        self.assertEqual(AppearanceService.resolve_object_type(fresh, type_id).shape, "star")
        self.assertTrue(AppearanceService.has_type_style(fresh, OBJECT_TYPE, type_id))

    def test_deleting_a_persisted_type_prunes_its_style(self):
        doomed = self.make_object_type("doomed")
        survivor = self.make_object_type("survivor")
        AppearanceService.set_type_style(self.model, OBJECT_TYPE, doomed.id, "shape", "star")
        AppearanceService.set_type_style(self.model, OBJECT_TYPE, survivor.id, "shape", "square")

        proposal = self.working_proposal()
        ProposalService.record_change(
            proposal=proposal,
            operation=ProposalChange.Operation.DELETE,
            target_type="ObjectType",
            target_id=doomed.id,
            parent_type="Model",
            parent_id=self.model.id,
            before=None,
            after=None,
        )
        ProposalService.submit(proposal)
        _drain(self.model.id)

        self.assertFalse(ObjectType.objects.filter(id=doomed.id).exists())
        fresh = Model.objects.get(pk=self.model.pk)
        self.assertFalse(AppearanceService.has_type_style(fresh, OBJECT_TYPE, doomed.id))
        self.assertTrue(AppearanceService.has_type_style(fresh, OBJECT_TYPE, survivor.id))

    def test_a_style_for_a_type_in_another_live_proposal_survives_abandon(self):
        other_user = CustomUser.objects.create_user(email="other@example.com", password="test-password")
        other_proposal = ProposalService.get_or_create_working(self.model, other_user)
        shared = self.propose_type(other_proposal, "ObjectType", "theirs")
        AppearanceService.set_type_style(self.model, OBJECT_TYPE, shared, "shape", "star")

        mine = self.working_proposal()
        self.propose_type(mine, "ObjectType", "mine")
        ProposalService.abandon(mine)

        self.assertTrue(AppearanceService.has_type_style(self.model, OBJECT_TYPE, shared))

    def test_prune_is_idempotent_and_leaves_model_layer_alone(self):
        AppearanceService.update_customisation(self.model, "theme", "accent", "#ff0000")
        AppearanceService.prune(self.model)
        AppearanceService.prune(self.model)

        self.assertEqual(AppearanceService.resolve_theme(self.model).accent, "#FF0000")

    def test_prune_does_not_touch_other_models(self):
        other = Model.objects.create(workspace=self.workspace, name="Other", revision=1)
        other_type = self.make_object_type("other", model=other)
        AppearanceService.set_type_style(other, OBJECT_TYPE, other_type.id, "shape", "star")

        AppearanceService.prune(self.model)

        self.assertTrue(AppearanceService.has_type_style(Model.objects.get(pk=other.pk), OBJECT_TYPE, other_type.id))
