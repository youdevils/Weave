from django.test import TestCase

from model.models.attribute_definition import AttributeDefinition
from model.models.model import Model
from model.models.object import Object
from model.models.object_type import ObjectType
from model.models.relationship import Relationship
from model.models.relationship_type import RelationshipType
from model.models.relationship_type_rule import RelationshipTypeRule
from model.services.validation.relationships import validate_relationship
from workspace.models import Workspace


class RelationshipValidationTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        # -----------------------------------------------------
        # Workspace and Models
        # -----------------------------------------------------

        cls.workspace = Workspace.objects.create(
            name="Test Workspace",
        )

        cls.model = Model.objects.create(
            workspace=cls.workspace,
            name="Test Model",
        )

        cls.other_model = Model.objects.create(
            workspace=cls.workspace,
            name="Other Model",
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

        cls.other_process_type = ObjectType.objects.create(
            model=cls.other_model,
            name="Process",
            key="process",
        )

        cls.other_system_type = ObjectType.objects.create(
            model=cls.other_model,
            name="System",
            key="system",
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

        cls.other_relationship_type = RelationshipType.objects.create(
            model=cls.other_model,
            name="Implements",
            key="implements",
        )

        # -----------------------------------------------------
        # Relationship Type Rules
        # -----------------------------------------------------

        RelationshipTypeRule.objects.create(
            relationship_type=cls.implements,
            subject_type=cls.process_type,
            object_type=cls.system_type,
        )

        RelationshipTypeRule.objects.create(
            relationship_type=cls.owned_by,
            subject_type=cls.process_type,
            object_type=cls.team_type,
        )

        RelationshipTypeRule.objects.create(
            relationship_type=cls.other_relationship_type,
            subject_type=cls.other_process_type,
            object_type=cls.other_system_type,
        )

        # -----------------------------------------------------
        # Objects
        # -----------------------------------------------------

        cls.process = Object.objects.create(
            model=cls.model,
            object_type=cls.process_type,
            name="Customer Payment",
        )

        cls.system = Object.objects.create(
            model=cls.model,
            object_type=cls.system_type,
            name="Gateway X",
        )

        cls.team = Object.objects.create(
            model=cls.model,
            object_type=cls.team_type,
            name="Payments Team",
        )

        cls.other_process = Object.objects.create(
            model=cls.other_model,
            object_type=cls.other_process_type,
            name="Other Process",
        )

        cls.other_system = Object.objects.create(
            model=cls.other_model,
            object_type=cls.other_system_type,
            name="Other System",
        )

    # ---------------------------------------------------------
    # Valid relationship
    # ---------------------------------------------------------

    def test_valid_relationship(self):
        relationship = Relationship(
            model=self.model,
            relationship_type=self.implements,
            subject=self.process,
            object=self.system,
        )

        result = validate_relationship(relationship)

        self.assertTrue(result.valid)
        self.assertEqual(result.issues, [])

    # ---------------------------------------------------------
    # Model consistency
    # ---------------------------------------------------------

    def test_relationship_type_must_belong_to_same_model(self):
        relationship = Relationship(
            model=self.model,
            relationship_type=self.other_relationship_type,
            subject=self.process,
            object=self.system,
        )

        result = validate_relationship(relationship)

        self.assertFalse(result.valid)

        self.assertIn(
            "relationship_type_model_mismatch",
            [issue.code for issue in result.issues],
        )

    def test_subject_must_belong_to_same_model(self):
        relationship = Relationship(
            model=self.model,
            relationship_type=self.implements,
            subject=self.other_process,
            object=self.system,
        )

        result = validate_relationship(relationship)

        self.assertFalse(result.valid)

        self.assertIn(
            "subject_model_mismatch",
            [issue.code for issue in result.issues],
        )

    def test_object_must_belong_to_same_model(self):
        relationship = Relationship(
            model=self.model,
            relationship_type=self.implements,
            subject=self.process,
            object=self.other_system,
        )

        result = validate_relationship(relationship)

        self.assertFalse(result.valid)

        self.assertIn(
            "object_model_mismatch",
            [issue.code for issue in result.issues],
        )

    # ---------------------------------------------------------
    # Relationship type rules
    # ---------------------------------------------------------

    def test_invalid_subject_type_is_rejected(self):
        relationship = Relationship(
            model=self.model,
            relationship_type=self.implements,
            subject=self.team,
            object=self.system,
        )

        result = validate_relationship(relationship)

        self.assertFalse(result.valid)

        self.assertIn(
            "invalid_relationship_types",
            [issue.code for issue in result.issues],
        )

    def test_invalid_object_type_is_rejected(self):
        relationship = Relationship(
            model=self.model,
            relationship_type=self.implements,
            subject=self.process,
            object=self.team,
        )

        result = validate_relationship(relationship)

        self.assertFalse(result.valid)

        self.assertIn(
            "invalid_relationship_types",
            [issue.code for issue in result.issues],
        )

    # ---------------------------------------------------------
    # Relationship attributes
    # ---------------------------------------------------------

    def test_relationship_attributes_are_validated(self):
        AttributeDefinition.objects.create(
            relationship_type=self.implements,
            name="Status",
            key="status",
            data_type=AttributeDefinition.DataType.TEXT,
        )

        relationship = Relationship(
            model=self.model,
            relationship_type=self.implements,
            subject=self.process,
            object=self.system,
            attributes={
                "status": 123,
            },
        )

        result = validate_relationship(relationship)

        self.assertFalse(result.valid)

        self.assertIn(
            "invalid_attribute_type",
            [issue.code for issue in result.issues],
        )

    def test_unknown_relationship_attributes_are_rejected(self):
        relationship = Relationship(
            model=self.model,
            relationship_type=self.implements,
            subject=self.process,
            object=self.system,
            attributes={
                "unknown": "value",
            },
        )

        result = validate_relationship(relationship)

        self.assertFalse(result.valid)

        self.assertIn(
            "unknown_attribute",
            [issue.code for issue in result.issues],
        )

    def test_required_relationship_attributes_are_enforced(self):
        AttributeDefinition.objects.create(
            relationship_type=self.implements,
            name="Status",
            key="status",
            data_type=AttributeDefinition.DataType.TEXT,
            required=True,
        )

        relationship = Relationship(
            model=self.model,
            relationship_type=self.implements,
            subject=self.process,
            object=self.system,
            attributes={},
        )

        result = validate_relationship(relationship)

        self.assertFalse(result.valid)

        self.assertIn(
            "required_attribute",
            [issue.code for issue in result.issues],
        )

    def test_optional_relationship_attributes_can_be_omitted(self):
        AttributeDefinition.objects.create(
            relationship_type=self.implements,
            name="Status",
            key="status",
            data_type=AttributeDefinition.DataType.TEXT,
            required=False,
        )

        relationship = Relationship(
            model=self.model,
            relationship_type=self.implements,
            subject=self.process,
            object=self.system,
            attributes={},
        )

        result = validate_relationship(relationship)

        self.assertTrue(result.valid)
        self.assertEqual(result.issues, [])

    # ---------------------------------------------------------
    # Multiple errors
    # ---------------------------------------------------------

    def test_multiple_relationship_errors_are_returned(self):
        relationship = Relationship(
            model=self.model,
            relationship_type=self.implements,
            subject=self.team,
            object=self.team,
            attributes={
                "unknown": "value",
            },
        )

        result = validate_relationship(relationship)

        self.assertFalse(result.valid)

        issue_codes = [issue.code for issue in result.issues]

        self.assertIn(
            "invalid_relationship_types",
            issue_codes,
        )

        self.assertIn(
            "unknown_attribute",
            issue_codes,
        )
