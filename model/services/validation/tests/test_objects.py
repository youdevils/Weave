from django.test import TestCase

from model.models.attribute_definition import AttributeDefinition
from model.models.model import Model
from model.models.object import Object
from model.models.object_type import ObjectType
from model.services.validation.object import validate_object
from workspace.models import Workspace


class ObjectValidationTests(TestCase):

    @classmethod
    def setUpTestData(cls):
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

        cls.object_type = ObjectType.objects.create(
            model=cls.model,
            name="System",
            key="system",
        )

        cls.other_object_type = ObjectType.objects.create(
            model=cls.other_model,
            name="Other System",
            key="other_system",
        )

    def test_valid_object(self):
        AttributeDefinition.objects.create(
            object_type=self.object_type,
            name="Lifecycle",
            key="lifecycle",
            data_type=AttributeDefinition.DataType.TEXT,
            required=True,
        )

        obj = Object(
            model=self.model,
            object_type=self.object_type,
            name="Gateway X",
            attributes={
                "lifecycle": "active",
            },
        )

        result = validate_object(obj)

        self.assertTrue(result.valid)
        self.assertEqual(result.issues, [])

    def test_object_type_must_belong_to_same_model(self):
        obj = Object(
            model=self.model,
            object_type=self.other_object_type,
            name="Gateway X",
            attributes={},
        )

        result = validate_object(obj)

        self.assertFalse(result.valid)

        self.assertIn(
            "object_type_model_mismatch",
            [issue.code for issue in result.issues],
        )

    def test_object_attributes_are_validated(self):
        AttributeDefinition.objects.create(
            object_type=self.object_type,
            name="Criticality",
            key="criticality",
            data_type=AttributeDefinition.DataType.NUMBER,
        )

        obj = Object(
            model=self.model,
            object_type=self.object_type,
            name="Gateway X",
            attributes={
                "criticality": "high",
            },
        )

        result = validate_object(obj)

        self.assertFalse(result.valid)

        self.assertIn(
            "invalid_attribute_type",
            [issue.code for issue in result.issues],
        )

    def test_unknown_attributes_are_rejected(self):
        obj = Object(
            model=self.model,
            object_type=self.object_type,
            name="Gateway X",
            attributes={
                "made_up": "value",
            },
        )

        result = validate_object(obj)

        self.assertFalse(result.valid)

        self.assertIn(
            "unknown_attribute",
            [issue.code for issue in result.issues],
        )

    def test_required_attributes_are_enforced(self):
        AttributeDefinition.objects.create(
            object_type=self.object_type,
            name="Lifecycle",
            key="lifecycle",
            data_type=AttributeDefinition.DataType.TEXT,
            required=True,
        )

        obj = Object(
            model=self.model,
            object_type=self.object_type,
            name="Gateway X",
            attributes={},
        )

        result = validate_object(obj)

        self.assertFalse(result.valid)

        self.assertIn(
            "required_attribute",
            [issue.code for issue in result.issues],
        )

    def test_optional_attributes_can_be_omitted(self):
        AttributeDefinition.objects.create(
            object_type=self.object_type,
            name="Lifecycle",
            key="lifecycle",
            data_type=AttributeDefinition.DataType.TEXT,
            required=False,
        )

        obj = Object(
            model=self.model,
            object_type=self.object_type,
            name="Gateway X",
            attributes={},
        )

        result = validate_object(obj)

        self.assertTrue(result.valid)
        self.assertEqual(result.issues, [])
