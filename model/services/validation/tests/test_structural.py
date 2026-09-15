from django.test import TestCase

from model.models.attribute_definition import AttributeDefinition
from model.models.model import Model
from model.models.object_type import ObjectType
from model.models.relationship_type import RelationshipType
from model.models.relationship_type_rule import RelationshipTypeRule
from model.services.validation.structural import (
    validate_attribute_definition,
    validate_relationship_type_rule,
)
from workspace.models import Workspace


class StructuralValidationTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.workspace = Workspace.objects.create(name="Test Workspace")

        cls.model = Model.objects.create(
            workspace=cls.workspace,
            name="Test Model",
        )

        cls.object_type = ObjectType.objects.create(
            model=cls.model,
            name="Person",
            key="person",
        )

        cls.other_object_type = ObjectType.objects.create(
            model=cls.model,
            name="Team",
            key="team",
        )

        cls.relationship_type = RelationshipType.objects.create(
            model=cls.model,
            name="Manages",
            key="manages",
        )

    # ---------------------------------------------------------
    # AttributeDefinition
    # ---------------------------------------------------------

    def test_valid_attribute_definition_has_no_issues(self):
        definition = AttributeDefinition(
            object_type=self.object_type,
            name="Email",
            key="email",
            data_type=AttributeDefinition.DataType.TEXT,
        )

        result = validate_attribute_definition(definition)

        self.assertTrue(result.valid)

    def test_attribute_definition_with_both_parents_is_invalid(self):
        definition = AttributeDefinition(
            object_type=self.object_type,
            relationship_type=self.relationship_type,
            name="Email",
            key="email",
            data_type=AttributeDefinition.DataType.TEXT,
        )

        result = validate_attribute_definition(definition)

        self.assertFalse(result.valid)
        self.assertEqual(result.issues[0].target_type, "AttributeDefinition")

    def test_attribute_definition_with_no_parent_is_invalid(self):
        definition = AttributeDefinition(
            name="Email",
            key="email",
            data_type=AttributeDefinition.DataType.TEXT,
        )

        result = validate_attribute_definition(definition)

        self.assertFalse(result.valid)

    def test_attribute_definition_bad_config_is_invalid(self):
        definition = AttributeDefinition(
            object_type=self.object_type,
            name="Age",
            key="age",
            data_type=AttributeDefinition.DataType.NUMBER,
            config={"min": 10, "max": 5},
        )

        result = validate_attribute_definition(definition)

        self.assertFalse(result.valid)

    # ---------------------------------------------------------
    # RelationshipTypeRule
    # ---------------------------------------------------------

    def test_valid_rule_has_no_issues(self):
        rule = RelationshipTypeRule(
            relationship_type=self.relationship_type,
            subject_type=self.object_type,
            object_type=self.other_object_type,
            subject_minimum=0,
            subject_maximum=1,
            object_minimum=0,
            object_maximum=None,
        )

        result = validate_relationship_type_rule(rule)

        self.assertTrue(result.valid)

    def test_rule_with_min_greater_than_max_is_invalid(self):
        rule = RelationshipTypeRule(
            relationship_type=self.relationship_type,
            subject_type=self.object_type,
            object_type=self.other_object_type,
            subject_minimum=5,
            subject_maximum=1,
        )

        result = validate_relationship_type_rule(rule)

        self.assertFalse(result.valid)
        self.assertEqual(result.issues[0].target_type, "RelationshipTypeRule")
