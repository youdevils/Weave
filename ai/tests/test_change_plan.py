import uuid

from django.test import SimpleTestCase, override_settings

from model.services.model_graph.loader import load_effective_dataset

from ai.services.change_plan import (
    AttributeDefinitionConfig,
    ChangeAction,
    ChangePlan,
    EntityRef,
    FieldEntry,
    FieldValue,
    validate_change_plan,
)
from ai.tests.support import AIServiceTestCase


def _existing(id_):
    return EntityRef(kind="existing", id=str(id_))


def _new(token):
    return EntityRef(kind="new", id=token)


class FieldValueTests(SimpleTestCase):
    """
    FieldValue replaced ChangeAction.fields' old dict[str, Any] value type,
    which OpenAI Structured Outputs' strict mode cannot represent (no bare
    object/Any can declare additionalProperties: false). These exercise the
    closed set of shapes it now supports, and that .native() reconstructs
    exactly the Python value the rest of the compiler has always expected.
    """

    def test_string_value(self):
        self.assertEqual(FieldValue(string_value="x").native(), "x")

    def test_number_value(self):
        self.assertEqual(FieldValue(number_value=4.5).native(), 4.5)

    def test_boolean_value_false_is_not_mistaken_for_unset(self):
        # Must not fall through to a later branch just because the value is falsy.
        self.assertIs(FieldValue(boolean_value=False).native(), False)

    def test_entity_ref_value(self):
        ref = _existing(uuid.uuid4())
        self.assertEqual(FieldValue(entity_ref_value=ref).native(), ref)

    def test_config_value_strips_unset_keys(self):
        config = AttributeDefinitionConfig(choices=["a", "b"])
        self.assertEqual(FieldValue(config_value=config).native(), {"choices": ["a", "b"]})

    def test_all_unset_is_none(self):
        self.assertIsNone(FieldValue().native())

    def test_of_detects_entity_ref_shaped_dict(self):
        value = FieldValue.of({"kind": "existing", "id": "abc"})
        self.assertEqual(value.entity_ref_value, EntityRef(kind="existing", id="abc"))

    def test_of_detects_config_shaped_dict(self):
        value = FieldValue.of({"choices": ["a", "b"]})
        self.assertEqual(value.config_value, AttributeDefinitionConfig(choices=["a", "b"]))

    def test_of_bool_is_not_mistaken_for_number(self):
        # bool is an int subclass in Python -- must be checked first.
        value = FieldValue.of(True)
        self.assertTrue(value.boolean_value)
        self.assertIsNone(value.number_value)

    def test_of_int_becomes_number_value(self):
        self.assertEqual(FieldValue.of(5).number_value, 5.0)

    def test_of_is_idempotent_on_an_existing_field_value(self):
        original = FieldValue(string_value="x")
        self.assertIs(FieldValue.of(original), original)


class ChangeActionFieldsTests(SimpleTestCase):
    """ChangeAction.fields' dict-shorthand backward compatibility and the
    explicit list[FieldEntry] shape a real OpenAI response now produces."""

    def test_dict_shorthand_is_accepted_and_converted(self):
        action = ChangeAction(
            operation="update",
            target_type="Object",
            target_ref=_existing(uuid.uuid4()),
            fields={"name": "X"},
        )

        self.assertEqual(len(action.fields), 1)
        self.assertIsInstance(action.fields[0], FieldEntry)
        self.assertEqual(action.fields[0].key, "name")
        self.assertEqual(action.fields[0].value.native(), "X")

    def test_explicit_list_of_field_entry_is_accepted_directly(self):
        """The shape a real OpenAI structured-output response arrives as."""
        action = ChangeAction(
            operation="update",
            target_type="Object",
            target_ref=_existing(uuid.uuid4()),
            fields=[FieldEntry(key="name", value=FieldValue(string_value="X"))],
        )

        self.assertEqual(action.fields_dict(), {"name": "X"})

    def test_fields_dict_nests_attribute_prefixed_entries(self):
        action = ChangeAction(
            operation="create",
            target_type="Object",
            target_ref=_new("tmp:1"),
            fields={"name": "Widget", "attributes.cost": 42.5, "attributes.owner": "Alice"},
        )

        self.assertEqual(
            action.fields_dict(),
            {"name": "Widget", "attributes": {"cost": 42.5, "owner": "Alice"}},
        )

    def test_update_keeps_attribute_prefixed_key_literal_not_nested(self):
        """
        An UPDATE addresses one attribute at a time via the literal dotted
        key (model.services.proposal.submission._apply_attribute_update),
        so ai.services.proposal_compiler must read `action.fields` directly
        rather than through fields_dict() for an update -- this just pins
        that fields_dict() is never silently relied on for that path.
        """
        action = ChangeAction(
            operation="update",
            target_type="Object",
            target_ref=_existing(uuid.uuid4()),
            fields={"attributes.cost": 42.5},
        )

        self.assertEqual(action.fields[0].key, "attributes.cost")
        self.assertEqual(action.fields[0].value.native(), 42.5)

    def test_entity_refs_in_fields_detects_entity_ref_value(self):
        subject = _existing(uuid.uuid4())
        action = ChangeAction(
            operation="create",
            target_type="Relationship",
            target_ref=_new("tmp:rel"),
            fields={"subject_id": subject.model_dump(), "object_id": _new("tmp:obj").model_dump()},
        )

        refs = dict(action.entity_refs_in_fields())
        self.assertEqual(refs["subject_id"], subject)
        self.assertEqual(refs["object_id"], _new("tmp:obj"))

    def test_entity_refs_in_fields_ignores_scalar_fields(self):
        action = ChangeAction(
            operation="update",
            target_type="Object",
            target_ref=_existing(uuid.uuid4()),
            fields={"name": "X"},
        )

        self.assertEqual(action.entity_refs_in_fields(), [])


class ValidateChangePlanTests(AIServiceTestCase):

    def setUp(self):
        self.model = self.make_model()
        self.object_type = self.make_object_type(self.model, key="widget")
        self.object = self.make_object(self.model, self.object_type, name="Widget 1")
        self.dataset = load_effective_dataset(self.model, proposal=None)

    def test_create_action_requires_new_target_ref(self):
        plan = ChangePlan(
            summary="",
            actions=[
                ChangeAction(
                    operation="create",
                    target_type="Object",
                    target_ref=_existing(self.object.id),
                    parent_ref=_existing(self.object_type.id),
                    fields={"name": "X"},
                )
            ],
        )

        issues = validate_change_plan(plan, dataset=self.dataset)

        self.assertTrue(any(issue.code == "create_requires_new_target_ref" for issue in issues))

    def test_update_action_requires_existing_target_ref(self):
        plan = ChangePlan(
            actions=[
                ChangeAction(
                    operation="update",
                    target_type="Object",
                    target_ref=_new("tmp:1"),
                    fields={"name": "X"},
                )
            ],
        )

        issues = validate_change_plan(plan, dataset=self.dataset)

        self.assertTrue(any(issue.code == "update_requires_existing_target_ref" for issue in issues))

    def test_delete_action_requires_existing_target_ref(self):
        plan = ChangePlan(
            actions=[
                ChangeAction(operation="delete", target_type="Object", target_ref=_new("tmp:1")),
            ],
        )

        issues = validate_change_plan(plan, dataset=self.dataset)

        self.assertTrue(any(issue.code == "delete_requires_existing_target_ref" for issue in issues))

    def test_update_action_with_no_fields_is_rejected(self):
        plan = ChangePlan(
            actions=[
                ChangeAction(
                    operation="update",
                    target_type="Object",
                    target_ref=_existing(self.object.id),
                    fields={},
                )
            ],
        )

        issues = validate_change_plan(plan, dataset=self.dataset)

        self.assertTrue(any(issue.code == "update_requires_at_least_one_field" for issue in issues))

    def test_existing_ref_must_resolve_against_canonical_dataset(self):
        plan = ChangePlan(
            actions=[
                ChangeAction(
                    operation="update",
                    target_type="Object",
                    target_ref=_existing(uuid.uuid4()),
                    fields={"name": "X"},
                )
            ],
        )

        issues = validate_change_plan(plan, dataset=self.dataset)

        self.assertTrue(any(issue.code == "unresolvable_existing_reference" for issue in issues))

    def test_new_ref_must_be_defined_by_exactly_one_create_action(self):
        relationship_type = self.make_relationship_type(self.model, key="depends_on")
        plan = ChangePlan(
            actions=[
                ChangeAction(
                    operation="create",
                    target_type="Relationship",
                    target_ref=_new("tmp:rel"),
                    parent_ref=_existing(relationship_type.id),
                    fields={
                        "subject_id": _existing(self.object.id).model_dump(),
                        "object_id": _new("tmp:ghost").model_dump(),
                    },
                )
            ],
        )

        issues = validate_change_plan(plan, dataset=self.dataset)

        self.assertTrue(any(issue.code == "dangling_temp_reference" for issue in issues))

    def test_validate_change_plan_flags_update_of_new_entity_created_in_same_plan(self):
        plan = ChangePlan(
            actions=[
                ChangeAction(
                    operation="create",
                    target_type="Object",
                    target_ref=_new("tmp:1"),
                    parent_ref=_existing(self.object_type.id),
                    fields={"name": "New widget"},
                ),
                ChangeAction(
                    operation="update",
                    target_type="Object",
                    target_ref=_new("tmp:1"),
                    fields={"name": "Renamed"},
                ),
            ],
        )

        issues = validate_change_plan(plan, dataset=self.dataset)

        self.assertTrue(
            any(issue.code == "unsupported_same_plan_update_of_new_entity" for issue in issues)
        )

    @override_settings(AI_MAX_CHANGE_PLAN_ACTIONS=1)
    def test_plan_over_max_actions_is_rejected(self):
        plan = ChangePlan(
            actions=[
                ChangeAction(
                    operation="update",
                    target_type="Object",
                    target_ref=_existing(self.object.id),
                    fields={"name": "A"},
                ),
                ChangeAction(
                    operation="update",
                    target_type="Object",
                    target_ref=_existing(self.object.id),
                    fields={"name": "B"},
                ),
            ],
        )

        issues = validate_change_plan(plan, dataset=self.dataset)

        self.assertTrue(any(issue.code == "change_plan_too_large" for issue in issues))

    def test_well_formed_plan_has_no_issues(self):
        plan = ChangePlan(
            summary="Create a new widget.",
            actions=[
                ChangeAction(
                    operation="create",
                    target_type="Object",
                    target_ref=_new("tmp:1"),
                    parent_ref=_existing(self.object_type.id),
                    fields={"name": "New widget"},
                    rationale="The intent asked for a new widget.",
                ),
            ],
        )

        issues = validate_change_plan(plan, dataset=self.dataset)

        self.assertEqual(issues, [])
