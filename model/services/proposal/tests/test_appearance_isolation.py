"""
Regression coverage for the isolation between Model appearance/style and the
Proposal system.

Model.appearance is documented (model.models.model.Model.appearance,
model.services.appearance.service module docstring) as deliberately outside
the Proposal system: writes persist directly through AppearanceService, and
proposal processing must never read, copy, snapshot or overwrite it except
through AppearanceService.prune()'s narrow, idempotent orphan cleanup of
per-type style entries.

These tests exercise the full lifecycle described in the regression report:
create a model from a template (default styles), manually edit a style,
then submit/process an unrelated ("normal") proposal, and confirm the style
survives untouched -- in both directions (proposal processing must not
touch appearance; editing appearance must not touch proposal state).
"""

import uuid

from django.test import TestCase

from account.models import CustomUser
from model.models.model import Model
from model.models.object_type import ObjectType
from model.models.proposal import Proposal, ProposalChange
from model.services.appearance import OBJECT_TYPE, AppearanceService
from model.services.model_template.loader import instantiate_template_via_proposal
from model.services.proposal import submission
from model.services.proposal.proposal import ProposalService
from workspace.models import Workspace


def _drain(model_id):
    """Claim and process every queued proposal for a Model, synchronously."""
    while True:
        proposal = submission.claim_next(model_id)
        if proposal is None:
            return
        submission.process(proposal.id)


class AppearanceIsolationBase(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.workspace = Workspace.objects.create(name="Test Workspace")
        cls.user = CustomUser.objects.create_user(email="u@example.com", password="pw")

    def make_model(self, name="Test Model"):
        return Model.objects.create(workspace=self.workspace, name=name, revision=1)

    def submit_unrelated_object_type_rename(self, model, object_type):
        """A normal, non-style proposal: rename an ObjectType."""
        proposal = ProposalService.get_or_create_working(model, self.user)
        ProposalService.record_change(
            proposal=proposal,
            operation=ProposalChange.Operation.UPDATE,
            target_type="ObjectType",
            target_id=object_type.id,
            field="name",
            before={"field": "name", "value": object_type.name},
            after={"field": "name", "value": f"{object_type.name} Renamed"},
        )
        ProposalService.submit(proposal)
        return proposal


class StyleSurvivesProposalLifecycleTests(AppearanceIsolationBase):
    """Scenario A: a manually changed style survives an unrelated proposal's
    full submit/validate/process/commit lifecycle."""

    def test_style_change_survives_unrelated_proposal(self):
        model = self.make_model()
        object_type = ObjectType.objects.create(
            model=model, name="Process", key="process", is_active=True
        )

        AppearanceService.set_type_style(model, OBJECT_TYPE, object_type.id, "background", "#123456")
        self.assertEqual(
            AppearanceService.resolve_object_type(model, object_type.id).background, "#123456"
        )

        proposal = self.submit_unrelated_object_type_rename(model, object_type)
        _drain(model.id)

        proposal.refresh_from_db()
        self.assertEqual(proposal.status, Proposal.Status.COMPLETED)

        model.refresh_from_db()
        self.assertEqual(
            AppearanceService.resolve_object_type(model, object_type.id).background, "#123456"
        )

    def test_style_from_template_default_survives_unrelated_proposal(self):
        model = self.make_model()
        instantiate_template_via_proposal(model, "delivery_project", self.user)

        object_type = ObjectType.objects.filter(model=model).first()
        AppearanceService.set_type_style(model, OBJECT_TYPE, object_type.id, "background", "#654321")

        new_type_id = uuid.uuid4()
        proposal = ProposalService.get_or_create_working(model, self.user)
        ProposalService.record_change(
            proposal=proposal,
            operation=ProposalChange.Operation.CREATE,
            target_type="ObjectType",
            target_id=new_type_id,
            parent_type="Model",
            parent_id=model.id,
            before=None,
            after={
                "name": "Unrelated",
                "key": "unrelated",
                "description": "",
                "sort_order": 0,
                "is_active": True,
            },
        )
        ProposalService.submit(proposal)
        _drain(model.id)

        proposal.refresh_from_db()
        self.assertEqual(proposal.status, Proposal.Status.COMPLETED)

        model.refresh_from_db()
        self.assertEqual(
            AppearanceService.resolve_object_type(model, object_type.id).background, "#654321"
        )


class ProposalProcessingLeavesAppearanceByteForByteTests(AppearanceIsolationBase):
    """Scenario B: the complete appearance document, not just one field,
    survives a normal proposal's lifecycle unchanged."""

    def test_full_appearance_document_unchanged_after_processing(self):
        model = self.make_model()
        object_type = ObjectType.objects.create(
            model=model, name="Process", key="process", is_active=True
        )

        AppearanceService.update_customisation(model, "theme", "accent", "#00FF00")
        AppearanceService.set_type_style(model, OBJECT_TYPE, object_type.id, "background", "#111111")
        AppearanceService.set_type_style(model, OBJECT_TYPE, object_type.id, "icon", "flag")

        before_document = Model.objects.get(pk=model.pk).appearance

        self.submit_unrelated_object_type_rename(model, object_type)
        _drain(model.id)

        after_document = Model.objects.get(pk=model.pk).appearance
        self.assertEqual(before_document, after_document)


class AppearanceEditsDoNotLeakIntoProposalsTests(AppearanceIsolationBase):
    """Scenario C: setting a style never creates, nor is captured by, a
    ProposalChange -- appearance and proposal diffs are disjoint."""

    def test_appearance_writes_create_no_proposal_changes(self):
        model = self.make_model()
        object_type = ObjectType.objects.create(
            model=model, name="Process", key="process", is_active=True
        )

        self.assertEqual(ProposalChange.objects.filter(proposal__model=model).count(), 0)

        AppearanceService.set_type_style(model, OBJECT_TYPE, object_type.id, "background", "#222222")
        AppearanceService.update_customisation(model, "theme", "accent", "#333333")

        self.assertEqual(ProposalChange.objects.filter(proposal__model=model).count(), 0)

    def test_normal_proposal_diff_does_not_include_style_edit(self):
        model = self.make_model()
        object_type = ObjectType.objects.create(
            model=model, name="Process", key="process", is_active=True
        )

        AppearanceService.set_type_style(model, OBJECT_TYPE, object_type.id, "background", "#444444")

        proposal = self.submit_unrelated_object_type_rename(model, object_type)

        changes = list(proposal.changes.all())
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].target_type, "ObjectType")
        self.assertEqual((changes[0].after or {}).get("field"), "name")


class NewerStyleEditSurvivesProposalCompletionTests(AppearanceIsolationBase):
    """Scenario D: a style edit made *after* a proposal is created (while it
    is still open, or after it is queued) is not reverted when that
    proposal later completes."""

    def test_style_set_while_proposal_still_working_survives_its_own_completion(self):
        model = self.make_model()

        proposal = ProposalService.get_or_create_working(model, self.user)
        new_type_id = uuid.uuid4()
        ProposalService.record_change(
            proposal=proposal,
            operation=ProposalChange.Operation.CREATE,
            target_type="ObjectType",
            target_id=new_type_id,
            parent_type="Model",
            parent_id=model.id,
            before=None,
            after={
                "name": "Proposed",
                "key": "proposed",
                "description": "",
                "sort_order": 0,
                "is_active": True,
            },
        )

        # Style set on the still-proposed (not yet canonical) type, before
        # the proposal that creates it has completed.
        AppearanceService.set_type_style(model, OBJECT_TYPE, new_type_id, "background", "#ABCDEF")

        ProposalService.submit(proposal)
        _drain(model.id)

        proposal.refresh_from_db()
        self.assertEqual(proposal.status, Proposal.Status.COMPLETED)

        model.refresh_from_db()
        self.assertEqual(
            AppearanceService.resolve_object_type(model, new_type_id).background, "#ABCDEF"
        )

    def test_style_set_after_submit_but_before_process_is_not_reverted(self):
        model = self.make_model()
        object_type = ObjectType.objects.create(
            model=model, name="Process", key="process", is_active=True
        )

        self.submit_unrelated_object_type_rename(model, object_type)

        # The edit lands after submit (QUEUED) but before claim/process.
        AppearanceService.set_type_style(model, OBJECT_TYPE, object_type.id, "background", "#111111")

        claimed = submission.claim_next(model.id)
        submission.process(claimed.id)

        model.refresh_from_db()
        self.assertEqual(
            AppearanceService.resolve_object_type(model, object_type.id).background, "#111111"
        )


class ModelFieldUpdateCannotTargetAppearanceTests(AppearanceIsolationBase):
    """
    The defect this investigation found: model.services.proposal.submission's
    generic Model-field apply (_apply_model_field_update, used for CREATE-time
    ontology work like scope/description/purpose UPDATEs) accepted *any*
    attribute of the Model instance -- it checked ``hasattr(model, field)``
    rather than an explicit allow-list. model.views.overview.EDITABLE_FIELDS
    was the *only* thing stopping a Model-field ProposalChange naming
    "appearance" from being processed: nothing in the engine itself enforced
    the documented invariant that appearance is outside the Proposal system.

    No shipped UI path currently records such a change (overview.py's own
    EDITABLE_FIELDS check blocks it before it is ever created), but the
    engine must not rely solely on that one call site to keep this invariant.
    This proves the processing layer itself now rejects it, and that
    Model.appearance is untouched either way.
    """

    def test_a_model_field_change_naming_appearance_is_rejected_not_applied(self):
        model = self.make_model()
        AppearanceService.update_customisation(model, "theme", "accent", "#4C6EF5")
        before_document = Model.objects.get(pk=model.pk).appearance

        proposal = ProposalService.get_or_create_working(model, self.user)
        # Bypasses the view layer entirely, as a bug or a non-UI caller
        # (an API, an AI-agent integration) could.
        ProposalService.record_change(
            proposal=proposal,
            operation=ProposalChange.Operation.UPDATE,
            target_type="Model",
            target_id=model.id,
            field="appearance",
            before={"field": "appearance", "value": before_document},
            after={"field": "appearance", "value": {"poisoned": True}},
        )
        ProposalService.submit(proposal)
        _drain(model.id)

        proposal.refresh_from_db()
        self.assertEqual(proposal.status, Proposal.Status.FAILED)
        self.assertEqual(proposal.validation_status, Proposal.ValidationStatus.INVALID)

        model.refresh_from_db()
        self.assertEqual(model.appearance, before_document)
