from django.test import TestCase, TransactionTestCase

from account.models import CustomUser
from model.model_templates.business_process import BUSINESS_PROCESS_TEMPLATE
from model.model_templates.delivery_project import DELIVERY_PROJECT_TEMPLATE
from model.models.model import Model
from model.models.object import Object
from model.models.object_type import ObjectType
from model.models.proposal import Proposal, ProposalChange
from model.models.proposal_submission_result import ProposalSubmissionResult
from model.models.relationship import Relationship
from model.models.relationship_type import RelationshipType
from model.models.relationship_type_rule import RelationshipTypeRule
from model.services.appearance import AppearanceService, AppearanceValidationError
from model.services.model_template import loader
from model.services.model_template.loader import (
    TemplateInstantiationFailure,
    instantiate_template_via_proposal,
)
from workspace.models import Workspace


class Base(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.workspace = Workspace.objects.create(name="Test Workspace")
        cls.user = CustomUser.objects.create_user(email="u@example.com", password="pw")

    def make_model(self):
        return Model.objects.create(workspace=self.workspace, name="M")


class HarbourHomeRetailInstantiationTests(Base):

    def test_creates_a_completed_proposal_with_one_change_per_template_item(self):
        model = self.make_model()

        instantiate_template_via_proposal(model, "delivery_project", self.user)

        proposal = Proposal.objects.get(model=model)
        self.assertEqual(proposal.status, Proposal.Status.COMPLETED)
        self.assertEqual(proposal.validation_status, Proposal.ValidationStatus.VALID)
        self.assertEqual(
            proposal.title,
            "Initialise from Harbour Home Retail EFTPOS Modernisation template",
        )
        self.assertEqual(
            proposal.summary,
            "Create initial model from Harbour Home Retail EFTPOS Modernisation template",
        )

        template = DELIVERY_PROJECT_TEMPLATE
        self.assertEqual(
            ProposalChange.objects.filter(proposal=proposal, target_type="ObjectType").count(),
            len(template["object_types"]),
        )
        self.assertEqual(
            ProposalChange.objects.filter(proposal=proposal, target_type="RelationshipType").count(),
            len(template["relationship_types"]),
        )
        self.assertEqual(
            ProposalChange.objects.filter(proposal=proposal, target_type="Object").count(),
            len(template["objects"]),
        )
        self.assertEqual(
            ProposalChange.objects.filter(proposal=proposal, target_type="Relationship").count(),
            len(template["relationships"]),
        )

    def test_canonical_content_matches_the_template(self):
        model = self.make_model()

        instantiate_template_via_proposal(model, "delivery_project", self.user)

        template = DELIVERY_PROJECT_TEMPLATE
        self.assertEqual(ObjectType.objects.filter(model=model).count(), len(template["object_types"]))
        self.assertEqual(
            RelationshipType.objects.filter(model=model).count(), len(template["relationship_types"])
        )
        self.assertEqual(Object.objects.filter(model=model).count(), len(template["objects"]))
        self.assertEqual(Relationship.objects.filter(model=model).count(), len(template["relationships"]))

        expected_rules = sum(
            len(relationship_type.get("rules", [])) for relationship_type in template["relationship_types"]
        )
        self.assertEqual(
            RelationshipTypeRule.objects.filter(relationship_type__model=model).count(),
            expected_rules,
        )

    def test_bumps_model_revision_and_records_before_after(self):
        model = self.make_model()
        self.assertEqual(model.revision, 1)

        instantiate_template_via_proposal(model, "delivery_project", self.user)

        model.refresh_from_db()
        self.assertEqual(model.revision, 2)

        proposal = Proposal.objects.get(model=model)
        result = ProposalSubmissionResult.objects.get(proposal=proposal)
        self.assertEqual(result.before_revision, 1)
        self.assertEqual(result.after_revision, 2)
        self.assertEqual(result.outcome, ProposalSubmissionResult.Outcome.SUCCESS)

    def test_applies_template_appearance_to_canonical_type_ids(self):
        model = self.make_model()

        instantiate_template_via_proposal(model, "delivery_project", self.user)

        project_type = ObjectType.objects.get(model=model, key="project")
        object_appearance = AppearanceService.resolve_object_type(model, project_type.id)
        self.assertEqual(object_appearance.icon, "flag")
        self.assertEqual(object_appearance.shape, "hexagon")
        self.assertEqual(object_appearance.background, "#FFE8CC")

        depends_on_type = RelationshipType.objects.get(model=model, key="depends_on")
        relationship_appearance = AppearanceService.resolve_relationship_type(model, depends_on_type.id)
        self.assertEqual(relationship_appearance.colour, "#E03131")

    def test_appearance_write_does_not_bump_revision_a_second_time(self):
        model = self.make_model()

        instantiate_template_via_proposal(model, "delivery_project", self.user)

        model.refresh_from_db()
        # One bump from the proposal's own commit -- not a second one from
        # the appearance write that follows it.
        self.assertEqual(model.revision, 2)


class BusinessProcessInstantiationTests(Base):
    """
    Business Process's sample data has never actually been checked against
    validate_model() (it always bypassed validation via direct writes) --
    this is the deliberate, concrete answer to that risk: it must either
    complete cleanly, or fail cleanly with nothing left behind, never a
    partial or broken state.
    """

    def test_completes_or_fails_cleanly_with_no_partial_state(self):
        model = self.make_model()

        try:
            instantiate_template_via_proposal(model, "business_process", self.user)
        except TemplateInstantiationFailure:
            self.assertEqual(ObjectType.objects.filter(model=model).count(), 0)
            self.assertEqual(Object.objects.filter(model=model).count(), 0)
            self.assertEqual(Proposal.objects.filter(model=model).count(), 0)
        else:
            proposal = Proposal.objects.get(model=model)
            self.assertEqual(proposal.status, Proposal.Status.COMPLETED)
            self.assertEqual(
                ObjectType.objects.filter(model=model).count(),
                len(BUSINESS_PROCESS_TEMPLATE["object_types"]),
            )


class RollbackTests(TransactionTestCase):
    """
    A template that fails validation -- or whose declared appearance is
    invalid -- must leave nothing behind: no proposal, no changes, no
    canonical rows, no appearance write. Mirrors
    ingestion/tests/test_rollback.py's assert_nothing_left pattern.
    """

    def setUp(self):
        self.workspace = Workspace.objects.create(name="Test Workspace")
        self.user = CustomUser.objects.create_user(email="u@example.com", password="pw")
        self.model = Model.objects.create(workspace=self.workspace, name="M")

    def assert_nothing_left(self):
        self.assertEqual(Proposal.objects.filter(model=self.model).count(), 0)
        self.assertEqual(ProposalChange.objects.count(), 0)
        self.assertEqual(ObjectType.objects.filter(model=self.model).count(), 0)
        self.assertEqual(Object.objects.filter(model=self.model).count(), 0)

        self.model.refresh_from_db()
        self.assertEqual(self.model.revision, 1)
        self.assertEqual(self.model.appearance, {})

    def _register(self, key, template):
        loader.TEMPLATES[key] = template
        self.addCleanup(loader.TEMPLATES.pop, key, None)

    def test_a_template_that_fails_cardinality_validation_rolls_back(self):
        # "a" must have at least one "r" relationship to a "b", but none of
        # the sample data defines one -- validate_cardinality must reject it.
        broken_template = {
            "key": "broken-cardinality",
            "name": "Broken Cardinality",
            "description": "",
            "object_types": [
                {"key": "a", "name": "A", "description": "", "sort_order": 0, "attributes": []},
                {"key": "b", "name": "B", "description": "", "sort_order": 0, "attributes": []},
            ],
            "relationship_types": [
                {
                    "key": "r",
                    "name": "R",
                    "description": "",
                    "sort_order": 0,
                    "attributes": [],
                    "rules": [
                        {
                            "subject_type": "a",
                            "object_type": "b",
                            "subject_minimum": 0,
                            "subject_maximum": None,
                            "object_minimum": 1,
                            "object_maximum": None,
                        },
                    ],
                },
            ],
            "objects": [
                {"key": "a1", "type": "a", "name": "A1", "description": "", "attributes": {}},
                {"key": "b1", "type": "b", "name": "B1", "description": "", "attributes": {}},
            ],
            "relationships": [],
        }
        self._register("broken-cardinality", broken_template)

        with self.assertRaises(TemplateInstantiationFailure):
            instantiate_template_via_proposal(self.model, "broken-cardinality", self.user)

        self.assert_nothing_left()

    def test_a_template_with_an_invalid_appearance_value_rolls_back(self):
        broken_template = {
            "key": "broken-appearance",
            "name": "Broken Appearance",
            "description": "",
            "object_types": [
                {"key": "a", "name": "A", "description": "", "sort_order": 0, "attributes": []},
            ],
            "relationship_types": [],
            "objects": [],
            "relationships": [],
            "appearance": {
                "object_types": {"a": {"icon": "not-a-real-icon"}},
                "relationship_types": {},
            },
        }
        self._register("broken-appearance", broken_template)

        with self.assertRaises(AppearanceValidationError):
            instantiate_template_via_proposal(self.model, "broken-appearance", self.user)

        self.assert_nothing_left()
