from django.test import SimpleTestCase

from ai.services.operations import (
    DuplicateOperation,
    OperationDefinition,
    UnknownOperation,
    get_operation,
    list_operations,
    register_operation,
)
from ai.services.change_plan import ChangePlan


def _definition(operation_id):
    return OperationDefinition(
        operation_id=operation_id,
        name="Synthetic",
        description="",
        evidence="optional",
        can_produce_proposal=True,
        required_context_categories=frozenset(),
        input_schema=ChangePlan,
        output_schema=ChangePlan,
    )


class OperationRegistryTests(SimpleTestCase):

    def tearDown(self):
        from ai.services.operations import _unregister_operation

        _unregister_operation("synthetic_a")
        _unregister_operation("synthetic_b")

    def test_register_and_get_operation(self):
        register_operation(_definition("synthetic_a"))

        self.assertEqual(get_operation("synthetic_a").operation_id, "synthetic_a")

    def test_get_unknown_operation_raises(self):
        with self.assertRaises(UnknownOperation):
            get_operation("does_not_exist")

    def test_list_operations_returns_registered_definitions(self):
        register_operation(_definition("synthetic_a"))
        register_operation(_definition("synthetic_b"))

        ids = {definition.operation_id for definition in list_operations()}

        self.assertIn("synthetic_a", ids)
        self.assertIn("synthetic_b", ids)

    def test_registering_duplicate_id_raises(self):
        register_operation(_definition("synthetic_a"))

        with self.assertRaises(DuplicateOperation):
            register_operation(_definition("synthetic_a"))

    def test_no_real_operations_registered_this_phase(self):
        for operation_id in ("create", "reconcile", "change", "assess"):
            with self.assertRaises(UnknownOperation):
                get_operation(operation_id)
