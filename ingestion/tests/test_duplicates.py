from ingestion.services.proposals import preview_import
from ingestion.tests.base import ImportTestCase


class DuplicateSourceRowTests(ImportTestCase):

    MATCH = {"column": 0, "field": "attribute.app_id", "match": True}
    NAME = {"column": 1, "field": "field.name"}
    OWNER = {"column": 2, "field": "attribute.owner"}

    def plan(self, rows, *columns):
        source = self.stage(rows)
        return preview_import(self.model, source, self.object_mapping(*columns))

    def test_identical_duplicate_rows_collapse_to_one_result(self):
        plan = self.plan(
            [["App ID", "Name"], ["A1", "Payroll"], ["A1", "Payroll"]], self.MATCH, self.NAME
        )

        self.assertEqual(len(plan.changes), 1)
        self.assertEqual(plan.summary.creates, 1)
        self.assertEqual((plan.summary.duplicate_identities, plan.summary.duplicate_rows), (1, 2))

    def test_different_fields_across_rows_all_survive(self):
        self.make_app("Old", "A1")

        plan = self.plan(
            [["App ID", "Name", "Owner"], ["A1", "New name", ""], ["A1", "Old", "Finance"]],
            self.MATCH, self.NAME, self.OWNER,
        )

        # Row 2 sets the name (later overwritten back to canonical -> no change);
        # row 3 sets the owner.
        fields = {change.after["field"]: change.after["value"] for change in plan.changes}
        self.assertEqual(fields, {"attributes.owner": "Finance"})

    def test_the_later_row_wins_for_the_same_field(self):
        app = self.make_app("Old", "A1")

        plan = self.plan(
            [["App ID", "Name"], ["A1", "New A"], ["A1", "New B"]], self.MATCH, self.NAME
        )

        (change,) = plan.changes
        self.assertEqual(change.target_id, app.id)
        self.assertEqual(change.before, {"field": "name", "value": "Old"})
        self.assertEqual(change.after, {"field": "name", "value": "New B"})

    def test_no_intermediate_change_is_emitted(self):
        self.make_app("Old", "A1")

        plan = self.plan(
            [["App ID", "Name"], ["A1", "One"], ["A1", "Two"], ["A1", "Three"]], self.MATCH, self.NAME
        )

        self.assertEqual(len(plan.changes), 1)
        self.assertEqual(plan.changes[0].before["value"], "Old")
        self.assertEqual(plan.changes[0].after["value"], "Three")

    def test_a_blank_is_a_real_assignment_and_can_win(self):
        self.make_app("Payroll", "A1", owner="Finance")

        plan = self.plan(
            [["App ID", "Owner"], ["A1", "HR"], ["A1", ""]],
            self.MATCH, {"column": 1, "field": "attribute.owner"},
        )

        (change,) = plan.changes
        self.assertEqual(change.after, {"field": "attributes.owner", "value": None})

    def test_a_later_value_can_supersede_an_earlier_blank(self):
        plan = self.plan(
            [["App ID", "Name", "Owner"], ["A1", "Payroll", ""], ["A1", "Payroll", "Finance"]],
            self.MATCH, self.NAME, self.OWNER,
        )

        self.assertEqual(plan.changes[0].after["attributes"]["owner"], "Finance")

    def test_returning_a_field_to_its_canonical_value_is_a_no_op(self):
        self.make_app("Old", "A1")

        plan = self.plan(
            [["App ID", "Name"], ["A1", "Changed"], ["A1", "Old"]], self.MATCH, self.NAME
        )

        self.assertEqual(plan.changes, [])
        self.assertEqual(plan.summary.no_ops, 1)

    def test_row_order_is_what_decides(self):
        self.make_app("Old", "A1")

        forward = self.plan([["App ID", "Name"], ["A1", "X"], ["A1", "Y"]], self.MATCH, self.NAME)
        backward = self.plan([["App ID", "Name"], ["A1", "Y"], ["A1", "X"]], self.MATCH, self.NAME)

        self.assertEqual(forward.changes[0].after["value"], "Y")
        self.assertEqual(backward.changes[0].after["value"], "X")

    def test_the_same_source_gives_the_same_plan_every_time(self):
        self.make_app("Old", "A1")
        rows = [["App ID", "Name", "Owner"], ["A1", "New", "X"], ["A2", "Two", "Y"], ["A1", "Newer", ""]]

        def shape(plan):
            return [(c.operation, c.before, c.after) for c in plan.changes]

        first = self.plan(rows, self.MATCH, self.NAME, self.OWNER)
        second = self.plan(rows, self.MATCH, self.NAME, self.OWNER)

        self.assertEqual(shape(first), shape(second))

    def test_rows_without_identity_never_collapse(self):
        plan = self.plan(
            [["Name"], ["Same"], ["Same"]], {"column": 0, "field": "field.name"}
        )

        self.assertEqual(plan.summary.creates, 2)
        self.assertEqual(plan.summary.duplicate_identities, 0)

    def test_relationship_rows_for_the_same_new_pair_are_one_create(self):
        a = self.make_app("Alpha", "A")
        b = self.make_app("Beta", "B")
        source = self.stage([["From", "To", "Since"], ["A", "B", "2020-01-01"], ["A", "B", "2021-01-01"]])

        plan = preview_import(
            self.model, source,
            self.relationship_mapping(
                self.by_app_id(0, "endpoint.subject"), self.by_app_id(1, "endpoint.object"),
                {"column": 2, "field": "attribute.since"},
            ),
        )

        (change,) = plan.changes
        self.assertEqual(change.after["attributes"], {"since": "2021-01-01"})
        self.assertEqual(plan.summary.duplicate_identities, 1)
