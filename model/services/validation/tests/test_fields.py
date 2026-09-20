from django.test import TestCase

from model.models.model import Model
from model.models.object import Object
from model.models.object_type import ObjectType
from model.models.relationship import Relationship
from model.models.relationship_type import RelationshipType
from model.models.relationship_type_rule import RelationshipTypeRule
from model.services.validation.fields import (
    NAME_MAX_LENGTH,
    validate_object_builtin_fields,
    validate_object_field,
    validate_relationship_builtin_fields,
    validate_relationship_field,
)
from model.services.validation.objects import validate_object
from model.services.validation.relationships import validate_relationship
from workspace.models import Workspace


def codes(issues):
    return [issue.code for issue in issues]


class ObjectFieldTests(TestCase):

    def test_a_normal_name_is_valid(self):
        self.assertIsNone(validate_object_field("name", "Payroll"))

    def test_a_blank_or_whitespace_name_is_required(self):
        self.assertEqual(validate_object_field("name", "").code, "name_required")
        self.assertEqual(validate_object_field("name", "   ").code, "name_required")

    def test_a_non_text_name_is_rejected(self):
        for value in (None, 5, True, ["x"]):
            self.assertEqual(validate_object_field("name", value).code, "invalid_name", repr(value))

    def test_the_name_length_matches_the_column(self):
        self.assertEqual(NAME_MAX_LENGTH, 255)
        self.assertIsNone(validate_object_field("name", "x" * 255))
        self.assertEqual(validate_object_field("name", "x" * 256).code, "name_too_long")

    def test_description_must_be_text_but_may_be_empty(self):
        self.assertIsNone(validate_object_field("description", ""))
        self.assertIsNone(validate_object_field("description", "words"))
        self.assertEqual(validate_object_field("description", None).code, "invalid_description")

    def test_is_active_must_be_a_boolean(self):
        self.assertIsNone(validate_object_field("is_active", True))
        self.assertIsNone(validate_object_field("is_active", False))

        for value in (None, "true", 1, 0, "maybe"):
            self.assertEqual(validate_object_field("is_active", value).code, "invalid_is_active", repr(value))

    def test_other_fields_are_not_judged_here(self):
        self.assertIsNone(validate_object_field("attributes", "anything"))
        self.assertIsNone(validate_object_field("something_else", None))

    def test_the_bundle_reports_every_problem(self):
        issues = validate_object_builtin_fields(name="", description=None, is_active="x")

        self.assertEqual(codes(issues), ["name_required", "invalid_description", "invalid_is_active"])
        self.assertEqual(validate_object_builtin_fields(name="A", description="", is_active=True), [])


class RelationshipFieldTests(TestCase):

    def test_is_active_must_be_a_boolean(self):
        self.assertIsNone(validate_relationship_field("is_active", True))
        self.assertEqual(validate_relationship_field("is_active", None).code, "invalid_is_active")
        self.assertIsNone(validate_relationship_field("attributes", None))
        self.assertEqual(codes(validate_relationship_builtin_fields(is_active="no")), ["invalid_is_active"])


class StoredStateValidationTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        workspace = Workspace.objects.create(name="W")
        cls.model = Model.objects.create(workspace=workspace, name="M")
        cls.object_type = ObjectType.objects.create(model=cls.model, name="Thing", key="thing")
        cls.relationship_type = RelationshipType.objects.create(model=cls.model, name="Rel", key="rel")
        RelationshipTypeRule.objects.create(
            relationship_type=cls.relationship_type, subject_type=cls.object_type, object_type=cls.object_type
        )

    def test_validate_object_flags_a_blank_name(self):
        obj = Object(model=self.model, object_type=self.object_type, name="")

        result = validate_object(obj)

        self.assertIn("name_required", codes(result.issues))
        self.assertEqual(result.issues[0].target_type, "Object")

    def test_validate_object_accepts_a_named_object(self):
        obj = Object(model=self.model, object_type=self.object_type, name="Thing 1")

        self.assertTrue(validate_object(obj).valid)

    def test_validate_relationship_flags_a_non_boolean_is_active(self):
        one = Object.objects.create(model=self.model, object_type=self.object_type, name="One")
        two = Object.objects.create(model=self.model, object_type=self.object_type, name="Two")
        relationship = Relationship(
            model=self.model, relationship_type=self.relationship_type, subject=one, object=two, is_active=None
        )

        self.assertIn("invalid_is_active", codes(validate_relationship(relationship).issues))
