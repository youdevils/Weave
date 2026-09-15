from django.test import TestCase

from model.models.attribute_definition import AttributeDefinition
from model.models.model import Model
from model.models.object import Object
from model.models.object_type import ObjectType
from model.models.relationship import Relationship
from model.models.relationship_type import RelationshipType
from model.models.relationship_type_rule import RelationshipTypeRule
from model.services.validation.model_validation import validate_model
from workspace.models import Workspace


class ModelValidationTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.workspace = Workspace.objects.create(name="Test Workspace")

        cls.model = Model.objects.create(
            workspace=cls.workspace,
            name="Test Model",
        )

        cls.person_type = ObjectType.objects.create(
            model=cls.model,
            name="Person",
            key="person",
        )

        cls.team_type = ObjectType.objects.create(
            model=cls.model,
            name="Team",
            key="team",
        )

        cls.member_of = RelationshipType.objects.create(
            model=cls.model,
            name="Member Of",
            key="member-of",
        )

    def test_clean_model_has_no_issues(self):
        result = validate_model(self.model)

        self.assertTrue(result.valid)

    def test_object_with_unknown_attribute_is_reported(self):
        AttributeDefinition.objects.create(
            object_type=self.person_type,
            name="Email",
            key="email",
            data_type=AttributeDefinition.DataType.TEXT,
        )

        obj = Object.objects.create(
            model=self.model,
            object_type=self.person_type,
            name="Alice",
            attributes={"unexpected": "value"},
        )

        result = validate_model(self.model)

        self.assertFalse(result.valid)
        codes = {issue.code for issue in result.issues}
        self.assertIn("unknown_attribute", codes)

        matching = [issue for issue in result.issues if issue.code == "unknown_attribute"]
        self.assertEqual(matching[0].target_type, "Object")
        self.assertEqual(matching[0].target_id, obj.id)

    def test_relationship_without_matching_rule_is_reported(self):
        subject = Object.objects.create(
            model=self.model, object_type=self.person_type, name="Alice"
        )
        obj = Object.objects.create(
            model=self.model, object_type=self.team_type, name="Engineering"
        )

        relationship = Relationship.objects.create(
            model=self.model,
            relationship_type=self.member_of,
            subject=subject,
            object=obj,
        )

        result = validate_model(self.model)

        self.assertFalse(result.valid)
        codes = {issue.code for issue in result.issues}
        self.assertIn("invalid_relationship_types", codes)

        matching = [
            issue for issue in result.issues if issue.code == "invalid_relationship_types"
        ]
        self.assertEqual(matching[0].target_type, "Relationship")
        self.assertEqual(matching[0].target_id, relationship.id)

    def test_cardinality_violation_is_reported(self):
        RelationshipTypeRule.objects.create(
            relationship_type=self.member_of,
            subject_type=self.person_type,
            object_type=self.team_type,
            object_required=True,
        )

        Object.objects.create(
            model=self.model, object_type=self.person_type, name="Alice"
        )

        result = validate_model(self.model)

        self.assertFalse(result.valid)
        codes = {issue.code for issue in result.issues}
        self.assertIn("object_required", codes)

    def test_structurally_invalid_attribute_definition_is_reported(self):
        AttributeDefinition.objects.create(
            object_type=self.person_type,
            name="Age",
            key="age",
            data_type=AttributeDefinition.DataType.NUMBER,
            config={"min": 10, "max": 5},
        )

        result = validate_model(self.model)

        self.assertFalse(result.valid)
        codes = {issue.code for issue in result.issues}
        self.assertIn("structural_invalid", codes)

    def test_structurally_invalid_rule_is_reported(self):
        RelationshipTypeRule.objects.create(
            relationship_type=self.member_of,
            subject_type=self.person_type,
            object_type=self.team_type,
            subject_minimum=5,
            subject_maximum=1,
        )

        result = validate_model(self.model)

        self.assertFalse(result.valid)
        codes = {issue.code for issue in result.issues}
        self.assertIn("structural_invalid", codes)
