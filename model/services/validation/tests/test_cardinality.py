from django.test import TestCase

from model.models.model import Model
from model.models.object import Object
from model.models.object_type import ObjectType
from model.models.relationship import Relationship
from model.models.relationship_type import RelationshipType
from model.models.relationship_type_rule import RelationshipTypeRule
from model.services.validation.cardinality import validate_cardinality
from workspace.models import Workspace


class CardinalityValidationTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        # -----------------------------------------------------
        # Workspace and Model
        # -----------------------------------------------------

        cls.workspace = Workspace.objects.create(
            name="Test Workspace",
        )

        cls.model = Model.objects.create(
            workspace=cls.workspace,
            name="Test Model",
        )

        # -----------------------------------------------------
        # Object Types
        # -----------------------------------------------------

        cls.process_type = ObjectType.objects.create(
            model=cls.model,
            name="Process",
            key="process",
        )

        cls.system_type = ObjectType.objects.create(
            model=cls.model,
            name="System",
            key="system",
        )

        cls.team_type = ObjectType.objects.create(
            model=cls.model,
            name="Team",
            key="team",
        )

        # -----------------------------------------------------
        # Relationship Types
        # -----------------------------------------------------

        cls.implements = RelationshipType.objects.create(
            model=cls.model,
            name="Implements",
            key="implements",
        )

        cls.owned_by = RelationshipType.objects.create(
            model=cls.model,
            name="Owned by",
            key="owned_by",
        )

        # -----------------------------------------------------
        # Relationship Type Rules
        # -----------------------------------------------------

        # Process may implement zero or more Systems.
        cls.implements_rule = RelationshipTypeRule.objects.create(
            relationship_type=cls.implements,
            subject_type=cls.process_type,
            object_type=cls.system_type,
            subject_minimum=0,
            subject_maximum=None,
            subject_required=False,
            object_minimum=0,
            object_maximum=None,
            object_required=False,
        )

        # Process must have exactly one Team.
        #
        # Object cardinality:
        #   Each Process must have exactly one Team.
        #
        # Subject cardinality:
        #   A Team has no minimum or maximum number of Processes.
        cls.owned_by_rule = RelationshipTypeRule.objects.create(
            relationship_type=cls.owned_by,
            subject_type=cls.process_type,
            object_type=cls.team_type,
            subject_minimum=0,
            subject_maximum=None,
            subject_required=False,
            object_minimum=1,
            object_maximum=1,
            object_required=True,
        )

        # -----------------------------------------------------
        # Objects
        # -----------------------------------------------------

        cls.process = Object.objects.create(
            model=cls.model,
            object_type=cls.process_type,
            name="Customer Payment",
        )

        cls.process_2 = Object.objects.create(
            model=cls.model,
            object_type=cls.process_type,
            name="Customer Refund",
        )

        cls.system = Object.objects.create(
            model=cls.model,
            object_type=cls.system_type,
            name="Gateway X",
        )

        cls.system_2 = Object.objects.create(
            model=cls.model,
            object_type=cls.system_type,
            name="Gateway Y",
        )

        cls.team = Object.objects.create(
            model=cls.model,
            object_type=cls.team_type,
            name="Payments Team",
        )

        cls.team_2 = Object.objects.create(
            model=cls.model,
            object_type=cls.team_type,
            name="Refunds Team",
        )

    # ---------------------------------------------------------
    # Valid model
    # ---------------------------------------------------------

    def test_valid_model(self):
        Relationship.objects.create(
            model=self.model,
            relationship_type=self.owned_by,
            subject=self.process,
            object=self.team,
        )

        Relationship.objects.create(
            model=self.model,
            relationship_type=self.owned_by,
            subject=self.process_2,
            object=self.team,
        )

        result = validate_cardinality(self.model)

        self.assertTrue(result.valid)
        self.assertEqual(result.issues, [])

    # ---------------------------------------------------------
    # Object minimum
    # ---------------------------------------------------------

    def test_object_minimum_is_enforced(self):
        result = validate_cardinality(self.model)

        self.assertFalse(result.valid)

        issue_codes = [issue.code for issue in result.issues]

        self.assertIn(
            "object_required",
            issue_codes,
        )

        self.assertIn(
            "object_cardinality_minimum",
            issue_codes,
        )

    def test_object_minimum_is_satisfied(self):
        Relationship.objects.create(
            model=self.model,
            relationship_type=self.owned_by,
            subject=self.process,
            object=self.team,
        )

        Relationship.objects.create(
            model=self.model,
            relationship_type=self.owned_by,
            subject=self.process_2,
            object=self.team,
        )

        result = validate_cardinality(self.model)

        self.assertTrue(result.valid)
        self.assertEqual(result.issues, [])

    # ---------------------------------------------------------
    # Object maximum
    # ---------------------------------------------------------

    def test_object_maximum_is_enforced(self):
        Relationship.objects.create(
            model=self.model,
            relationship_type=self.owned_by,
            subject=self.process,
            object=self.team,
        )

        Relationship.objects.create(
            model=self.model,
            relationship_type=self.owned_by,
            subject=self.process,
            object=self.team_2,
        )

        Relationship.objects.create(
            model=self.model,
            relationship_type=self.owned_by,
            subject=self.process_2,
            object=self.team,
        )

        result = validate_cardinality(self.model)

        self.assertFalse(result.valid)

        self.assertIn(
            "object_cardinality_maximum",
            [issue.code for issue in result.issues],
        )

    # ---------------------------------------------------------
    # Subject minimum
    # ---------------------------------------------------------

    def test_subject_minimum_is_enforced(self):
        self.owned_by_rule.subject_minimum = 1
        self.owned_by_rule.subject_required = True
        self.owned_by_rule.save()

        # Team has a Process.
        Relationship.objects.create(
            model=self.model,
            relationship_type=self.owned_by,
            subject=self.process,
            object=self.team,
        )

        # Team 2 has no Process.
        result = validate_cardinality(self.model)

        self.assertFalse(result.valid)

        issue_codes = [issue.code for issue in result.issues]

        self.assertIn(
            "subject_required",
            issue_codes,
        )

        self.assertIn(
            "subject_cardinality_minimum",
            issue_codes,
        )

    def test_subject_minimum_is_satisfied(self):
        self.owned_by_rule.subject_minimum = 1
        self.owned_by_rule.subject_required = True
        self.owned_by_rule.save()

        Relationship.objects.create(
            model=self.model,
            relationship_type=self.owned_by,
            subject=self.process,
            object=self.team,
        )

        Relationship.objects.create(
            model=self.model,
            relationship_type=self.owned_by,
            subject=self.process_2,
            object=self.team_2,
        )

        result = validate_cardinality(self.model)

        self.assertTrue(result.valid)
        self.assertEqual(result.issues, [])

    # ---------------------------------------------------------
    # Subject maximum
    # ---------------------------------------------------------

    def test_subject_maximum_is_enforced(self):
        self.owned_by_rule.subject_maximum = 1
        self.owned_by_rule.save()

        Relationship.objects.create(
            model=self.model,
            relationship_type=self.owned_by,
            subject=self.process,
            object=self.team,
        )

        Relationship.objects.create(
            model=self.model,
            relationship_type=self.owned_by,
            subject=self.process_2,
            object=self.team,
        )

        result = validate_cardinality(self.model)

        self.assertFalse(result.valid)

        self.assertIn(
            "subject_cardinality_maximum",
            [issue.code for issue in result.issues],
        )

    def test_subject_maximum_allows_relationships_up_to_limit(self):
        self.owned_by_rule.subject_maximum = 2
        self.owned_by_rule.save()

        Relationship.objects.create(
            model=self.model,
            relationship_type=self.owned_by,
            subject=self.process,
            object=self.team,
        )

        Relationship.objects.create(
            model=self.model,
            relationship_type=self.owned_by,
            subject=self.process_2,
            object=self.team,
        )

        result = validate_cardinality(self.model)

        self.assertTrue(result.valid)
        self.assertEqual(result.issues, [])

    # ---------------------------------------------------------
    # Unlimited maximum
    # ---------------------------------------------------------

    def test_unlimited_object_maximum_allows_multiple_relationships(self):
        Relationship.objects.create(
            model=self.model,
            relationship_type=self.implements,
            subject=self.process,
            object=self.system,
        )

        Relationship.objects.create(
            model=self.model,
            relationship_type=self.implements,
            subject=self.process,
            object=self.system_2,
        )

        Relationship.objects.create(
            model=self.model,
            relationship_type=self.owned_by,
            subject=self.process,
            object=self.team,
        )

        Relationship.objects.create(
            model=self.model,
            relationship_type=self.owned_by,
            subject=self.process_2,
            object=self.team,
        )

        result = validate_cardinality(self.model)

        self.assertTrue(result.valid)
        self.assertEqual(result.issues, [])

    # ---------------------------------------------------------
    # Rule isolation
    # ---------------------------------------------------------

    def test_cardinality_isolated_to_relationship_type_rule(self):
        # Implements allows unlimited relationships.
        Relationship.objects.create(
            model=self.model,
            relationship_type=self.implements,
            subject=self.process,
            object=self.system,
        )

        Relationship.objects.create(
            model=self.model,
            relationship_type=self.implements,
            subject=self.process,
            object=self.system_2,
        )

        # Owned By is independently satisfied.
        Relationship.objects.create(
            model=self.model,
            relationship_type=self.owned_by,
            subject=self.process,
            object=self.team,
        )

        Relationship.objects.create(
            model=self.model,
            relationship_type=self.owned_by,
            subject=self.process_2,
            object=self.team,
        )

        result = validate_cardinality(self.model)

        self.assertTrue(result.valid)
        self.assertEqual(result.issues, [])

    # ---------------------------------------------------------
    # Type isolation
    # ---------------------------------------------------------

    def test_relationship_to_wrong_object_type_does_not_count(self):
        # This relationship does not match the Owned By rule because
        # System is not the required object type.
        Relationship.objects.create(
            model=self.model,
            relationship_type=self.owned_by,
            subject=self.process,
            object=self.system,
        )

        result = validate_cardinality(self.model)

        self.assertFalse(result.valid)

        self.assertIn(
            "object_required",
            [issue.code for issue in result.issues],
        )

        self.assertIn(
            "object_cardinality_minimum",
            [issue.code for issue in result.issues],
        )

    # ---------------------------------------------------------
    # Inactive relationships
    # ---------------------------------------------------------

    def test_inactive_relationships_do_not_count(self):
        Relationship.objects.create(
            model=self.model,
            relationship_type=self.owned_by,
            subject=self.process,
            object=self.team,
            is_active=False,
        )

        Relationship.objects.create(
            model=self.model,
            relationship_type=self.owned_by,
            subject=self.process_2,
            object=self.team,
        )

        result = validate_cardinality(self.model)

        self.assertFalse(result.valid)

        self.assertIn(
            "object_required",
            [issue.code for issue in result.issues],
        )

    def test_active_relationships_count(self):
        Relationship.objects.create(
            model=self.model,
            relationship_type=self.owned_by,
            subject=self.process,
            object=self.team,
            is_active=True,
        )

        Relationship.objects.create(
            model=self.model,
            relationship_type=self.owned_by,
            subject=self.process_2,
            object=self.team,
            is_active=True,
        )

        result = validate_cardinality(self.model)

        self.assertTrue(result.valid)
        self.assertEqual(result.issues, [])

    # ---------------------------------------------------------
    # Inactive objects
    # ---------------------------------------------------------

    def test_inactive_subject_is_not_validated(self):
        self.process.is_active = False
        self.process.save()

        Relationship.objects.create(
            model=self.model,
            relationship_type=self.owned_by,
            subject=self.process_2,
            object=self.team,
        )

        result = validate_cardinality(self.model)

        self.assertTrue(result.valid)
        self.assertEqual(result.issues, [])

    def test_inactive_object_is_not_validated(self):
        self.team.is_active = False
        self.team.save()

        # The inactive Team is not itself required to have an incoming
        # relationship, but the active Process still requires an active
        # Team. Therefore the model remains invalid.
        Relationship.objects.create(
            model=self.model,
            relationship_type=self.owned_by,
            subject=self.process_2,
            object=self.team_2,
        )

        result = validate_cardinality(self.model)

        self.assertFalse(result.valid)

        self.assertIn(
            "object_required",
            [issue.code for issue in result.issues],
        )

    # ---------------------------------------------------------
    # Multiple errors
    # ---------------------------------------------------------

    def test_multiple_cardinality_errors_are_returned(self):
        self.owned_by_rule.subject_minimum = 1
        self.owned_by_rule.subject_required = True
        self.owned_by_rule.subject_maximum = 1
        self.owned_by_rule.save()

        result = validate_cardinality(self.model)

        self.assertFalse(result.valid)

        issue_codes = [issue.code for issue in result.issues]

        self.assertIn(
            "object_required",
            issue_codes,
        )

        self.assertIn(
            "object_cardinality_minimum",
            issue_codes,
        )

        self.assertIn(
            "subject_required",
            issue_codes,
        )

        self.assertIn(
            "subject_cardinality_minimum",
            issue_codes,
        )
