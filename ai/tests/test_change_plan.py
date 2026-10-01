import uuid

from django.test import override_settings

from model.services.model_graph.loader import load_effective_dataset

from ai.services.change_plan import ChangeAction, ChangePlan, EntityRef, validate_change_plan
from ai.tests.support import AIServiceTestCase


def _existing(id_):
    return EntityRef(kind="existing", id=str(id_))


def _new(token):
    return EntityRef(kind="new", id=token)


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
