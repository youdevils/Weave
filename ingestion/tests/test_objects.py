from ingestion.services.errors import MappingError, TargetError
from ingestion.services.proposals import preview_import
from ingestion.tests.base import ImportTestCase
from model.models.object import Object


def _by(plan, operation):
    return [change for change in plan.changes if change.operation == operation]


class ObjectImportTests(ImportTestCase):

    def plan(self, rows, *columns, **kwargs):
        source = self.stage(rows)
        return preview_import(self.model, source, self.object_mapping(*columns, **kwargs))

    MATCH = {"column": 0, "field": "attribute.app_id", "match": True}
    NAME = {"column": 1, "field": "field.name"}

    # -- CREATE ----------------------------------------------------------------

    def test_new_rows_create_objects_shaped_like_the_editor_payload(self):
        plan = self.plan(
            [["App ID", "Name", "Owner", "Cost"], ["A1", "Payroll", "Finance", "1200"]],
            self.MATCH, self.NAME,
            {"column": 2, "field": "attribute.owner"},
            {"column": 3, "field": "attribute.cost"},
        )

        self.assertFalse(plan.blocked)
        (change,) = plan.changes
        self.assertEqual(change.operation, "create")
        self.assertEqual(change.target_type, "Object")
        self.assertEqual(change.parent_type, "ObjectType")
        self.assertEqual(change.parent_id, self.app_type.id)
        self.assertIsNone(change.before)
        self.assertEqual(
            change.after,
            {
                "name": "Payroll",
                "description": "",
                "is_active": True,
                "attributes": {"app_id": "A1", "owner": "Finance", "cost": 1200},
            },
        )
        self.assertEqual((plan.summary.creates, plan.summary.updates, plan.summary.no_ops), (1, 0, 0))

    def test_creation_never_writes_the_canonical_model(self):
        self.plan([["App ID", "Name"], ["A1", "Payroll"]], self.MATCH, self.NAME)

        self.assertFalse(Object.objects.filter(model=self.model).exists())

    def test_new_object_has_a_generated_id_never_the_source_identity(self):
        plan = self.plan([["App ID", "Name"], ["A1", "Payroll"]], self.MATCH, self.NAME)

        self.assertNotEqual(str(plan.changes[0].target_id), "A1")
        self.assertEqual(len(str(plan.changes[0].target_id)), 36)

    def test_blank_attribute_on_create_is_left_out(self):
        plan = self.plan(
            [["App ID", "Name", "Owner"], ["A1", "Payroll", ""]],
            self.MATCH, self.NAME, {"column": 2, "field": "attribute.owner"},
        )

        self.assertEqual(plan.changes[0].after["attributes"], {"app_id": "A1"})

    def test_blank_match_value_provides_no_identity_and_is_left_out(self):
        plan = self.plan(
            [["App ID", "Name"], ["", "Payroll"], ["", "Rostering"]], self.MATCH, self.NAME
        )

        self.assertEqual(len(_by(plan, "create")), 2)
        self.assertEqual(plan.changes[0].after["attributes"], {})

    def test_blank_name_passes_through_for_the_proposal_validator(self):
        plan = self.plan([["App ID", "Name"], ["A1", ""]], self.MATCH, self.NAME)

        self.assertFalse(plan.blocked)
        self.assertEqual(plan.changes[0].after["name"], "")

    def test_is_active_blank_on_create_takes_the_default(self):
        plan = self.plan(
            [["App ID", "Name", "Active"], ["A1", "Payroll", ""]],
            self.MATCH, self.NAME, {"column": 2, "field": "field.is_active"},
        )

        self.assertIs(plan.changes[0].after["is_active"], True)

    def test_is_active_false_is_a_real_value(self):
        plan = self.plan(
            [["App ID", "Name", "Active"], ["A1", "Payroll", "no"]],
            self.MATCH, self.NAME, {"column": 2, "field": "field.is_active"},
        )

        self.assertIs(plan.changes[0].after["is_active"], False)

    # -- datatype handling -------------------------------------------------------

    def test_values_are_represented_per_datatype(self):
        plan = self.plan(
            [
                ["App ID", "Name", "Cost", "Live", "Go live", "Tier"],
                ["A1", "Payroll", "12.5", "Yes", "2024-05-01", "gold"],
            ],
            self.MATCH, self.NAME,
            {"column": 2, "field": "attribute.cost"},
            {"column": 3, "field": "attribute.live"},
            {"column": 4, "field": "attribute.go_live"},
            {"column": 5, "field": "attribute.tier"},
        )

        self.assertEqual(
            plan.changes[0].after["attributes"],
            {"app_id": "A1", "cost": 12.5, "live": True, "go_live": "2024-05-01", "tier": "gold"},
        )

    def test_an_unreadable_value_is_passed_through_for_the_validator(self):
        plan = self.plan(
            [["App ID", "Name", "Cost"], ["A1", "Payroll", "lots"]],
            self.MATCH, self.NAME, {"column": 2, "field": "attribute.cost"},
        )

        self.assertFalse(plan.blocked)
        self.assertEqual(plan.changes[0].after["attributes"]["cost"], "lots")
        self.assertEqual(plan.summary.unconverted_cells, 1)

    def test_a_choice_outside_the_configured_choices_is_not_judged_here(self):
        plan = self.plan(
            [["App ID", "Name", "Tier"], ["A1", "Payroll", "bronze"]],
            self.MATCH, self.NAME, {"column": 2, "field": "attribute.tier"},
        )

        self.assertFalse(plan.blocked)
        self.assertEqual(plan.changes[0].after["attributes"]["tier"], "bronze")

    # -- UPDATE / NO-OP ------------------------------------------------------------

    def test_unchanged_records_are_no_ops(self):
        self.make_app("Payroll", "A1", owner="Finance")

        plan = self.plan(
            [["App ID", "Name", "Owner"], ["A1", "Payroll", "Finance"]],
            self.MATCH, self.NAME, {"column": 2, "field": "attribute.owner"},
        )

        self.assertEqual(plan.changes, [])
        self.assertEqual(plan.summary.no_ops, 1)

    def test_changed_fields_become_one_update_each_from_canonical_before(self):
        app = self.make_app("Payroll", "A1", owner="Finance")

        plan = self.plan(
            [["App ID", "Name", "Owner"], ["A1", "Payroll v2", "HR"]],
            self.MATCH, self.NAME, {"column": 2, "field": "attribute.owner"},
        )

        self.assertEqual(len(plan.changes), 2)
        by_field = {change.after["field"]: change for change in plan.changes}
        self.assertEqual(by_field["name"].before, {"field": "name", "value": "Payroll"})
        self.assertEqual(by_field["name"].after, {"field": "name", "value": "Payroll v2"})
        self.assertEqual(by_field["attributes.owner"].before, {"field": "attributes.owner", "value": "Finance"})
        self.assertEqual(by_field["attributes.owner"].after, {"field": "attributes.owner", "value": "HR"})
        self.assertTrue(all(change.target_id == app.id for change in plan.changes))
        self.assertTrue(all(change.operation == "update" for change in plan.changes))
        self.assertEqual((plan.summary.updates, plan.summary.field_changes), (1, 2))

    def test_unmapped_fields_are_left_untouched(self):
        self.make_app("Payroll", "A1", owner="Finance")

        plan = self.plan([["App ID", "Name"], ["A1", "Payroll"]], self.MATCH, self.NAME)

        self.assertEqual(plan.changes, [])

    def test_blank_on_update_sets_the_value_to_empty(self):
        self.make_app("Payroll", "A1", owner="Finance")

        plan = self.plan(
            [["App ID", "Owner"], ["A1", ""]], self.MATCH, {"column": 1, "field": "attribute.owner"}
        )

        (change,) = plan.changes
        self.assertEqual(change.after, {"field": "attributes.owner", "value": None})
        self.assertEqual(change.before, {"field": "attributes.owner", "value": "Finance"})

    def test_blank_over_a_missing_value_is_a_no_op(self):
        self.make_app("Payroll", "A1")

        plan = self.plan(
            [["App ID", "Owner"], ["A1", ""]], self.MATCH, {"column": 1, "field": "attribute.owner"}
        )

        self.assertEqual(plan.changes, [])

    def test_blank_name_and_description_become_empty_strings(self):
        self.make_app("Payroll", "A1")

        plan = self.plan(
            [["App ID", "Name", "Description"], ["A1", "", ""]],
            self.MATCH, self.NAME, {"column": 2, "field": "field.description"},
        )

        self.assertEqual(plan.changes[0].after, {"field": "name", "value": ""})

    def test_blank_is_active_on_update_is_none_and_left_to_the_validator(self):
        self.make_app("Payroll", "A1")

        plan = self.plan(
            [["App ID", "Active"], ["A1", ""]], self.MATCH, {"column": 1, "field": "field.is_active"}
        )

        self.assertEqual(plan.changes[0].after, {"field": "is_active", "value": None})

    def test_is_active_false_is_an_ordinary_update(self):
        self.make_app("Payroll", "A1")

        plan = self.plan(
            [["App ID", "Active"], ["A1", "false"]], self.MATCH, {"column": 1, "field": "field.is_active"}
        )

        self.assertEqual(plan.changes[0].after, {"field": "is_active", "value": False})
        self.assertEqual(plan.changes[0].before, {"field": "is_active", "value": True})

    def test_a_boolean_never_equals_a_number(self):
        self.make_app("Payroll", "A1", cost=1)

        plan = self.plan(
            [["App ID", "Cost"], ["A1", "true"]], self.MATCH, {"column": 1, "field": "attribute.cost"}
        )

        # "true" is not a number: passed through as text, not silently equal to 1.
        self.assertEqual(len(plan.changes), 1)
        self.assertEqual(plan.changes[0].after["value"], "true")

    def test_one_equals_one_point_zero(self):
        self.make_app("Payroll", "A1", cost=1)

        plan = self.plan(
            [["App ID", "Cost"], ["A1", "1.0"]], self.MATCH, {"column": 1, "field": "attribute.cost"}
        )

        self.assertEqual(plan.changes, [])

    # -- identity: OnyxJar Object ID ----------------------------------------------------

    def test_weave_object_id_identifies_the_existing_object(self):
        app = self.make_app("Payroll")

        plan = self.plan(
            [["ID", "Name"], [str(app.id), "Payroll v2"]],
            {"column": 0, "field": "identity.id"}, self.NAME | {"column": 1},
        )

        self.assertEqual(plan.changes[0].target_id, app.id)
        self.assertEqual(plan.changes[0].operation, "update")

    def test_an_id_that_does_not_resolve_is_blocking_with_no_fallback(self):
        self.make_app("Payroll", "A1")

        plan = self.plan(
            [["ID", "App ID", "Name"], [self.new_id(), "A1", "X"]],
            {"column": 0, "field": "identity.id"},
            {"column": 1, "field": "attribute.app_id", "match": True},
            {"column": 2, "field": "field.name"},
        )

        self.assertTrue(plan.blocked)
        self.assertEqual(plan.problems[0].code, "unresolved_identity")
        self.assertEqual(plan.problems[0].row, 2)
        self.assertEqual(plan.changes, [])

    def test_a_malformed_id_is_blocking(self):
        plan = self.plan(
            [["ID", "Name"], ["not-a-uuid", "X"]],
            {"column": 0, "field": "identity.id"}, {"column": 1, "field": "field.name"},
        )

        self.assertEqual(plan.problems[0].code, "invalid_identity_id")

    def test_an_id_of_another_object_type_is_blocking(self):
        person = self.make_app("Ann", object_type=self.person_type)

        plan = self.plan(
            [["ID", "Name"], [str(person.id), "X"]],
            {"column": 0, "field": "identity.id"}, {"column": 1, "field": "field.name"},
        )

        self.assertEqual(plan.problems[0].code, "wrong_object_type")

    def test_an_id_from_another_model_reads_as_not_found(self):
        foreign = self.make_app("Foreign", model=self.other_model, object_type=self.other_app_type)

        plan = self.plan(
            [["ID", "Name"], [str(foreign.id), "X"]],
            {"column": 0, "field": "identity.id"}, {"column": 1, "field": "field.name"},
        )

        self.assertEqual(plan.problems[0].code, "unresolved_identity")
        self.assertNotIn("different", plan.problems[0].message)

    # -- identity: match attribute ----------------------------------------------------

    def test_exactly_one_match_identifies_the_existing_object(self):
        app = self.make_app("Payroll", "A1")

        plan = self.plan([["App ID", "Name"], ["A1", "Payroll v2"]], self.MATCH, self.NAME)

        self.assertEqual({change.target_id for change in plan.changes}, {app.id})

    def test_no_match_creates(self):
        self.make_app("Payroll", "A1")

        plan = self.plan([["App ID", "Name"], ["A2", "Rostering"]], self.MATCH, self.NAME)

        self.assertEqual(len(_by(plan, "create")), 1)

    def test_multiple_matches_are_a_blocking_ambiguity(self):
        self.make_app("One", "A1")
        self.make_app("Two", "A1")

        plan = self.plan([["App ID", "Name"], ["A1", "X"]], self.MATCH, self.NAME)

        self.assertTrue(plan.blocked)
        self.assertEqual(plan.problems[0].code, "ambiguous_identity")

    def test_matching_is_exact_and_case_sensitive(self):
        self.make_app("Payroll", "app-001")

        plan = self.plan([["App ID", "Name"], ["APP-001", "X"]], self.MATCH, self.NAME)

        self.assertEqual(len(_by(plan, "create")), 1)

    def test_display_name_is_never_an_identity(self):
        self.make_app("Payroll", "A1")

        plan = self.plan([["Name"], ["Payroll"]], {"column": 0, "field": "field.name"})

        self.assertEqual(len(_by(plan, "create")), 1)
        self.assertIn("No identity column", plan.summary.warnings[0])

    def test_source_value_is_normalised_once_for_matching_and_writing(self):
        self.make_app("Payroll", "APP-001")

        plan = self.plan([["App ID", "Name"], ["  APP-001  ", "Payroll v2"]], self.MATCH, self.NAME)

        # Matched the trimmed value ...
        self.assertEqual({change.operation for change in plan.changes}, {"update"})

        # ... and a CREATE writes the same trimmed value.
        created = self.plan([["App ID", "Name"], ["  APP-777  ", "New"]], self.MATCH, self.NAME)
        self.assertEqual(created.changes[0].after["attributes"]["app_id"], "APP-777")

    def test_canonical_values_are_never_modified_by_matching(self):
        app = self.make_app("Payroll", "  spaced  ")

        plan = self.plan([["App ID", "Name"], ["spaced", "X"]], self.MATCH, self.NAME)

        # No trimmed-equivalence: canonical "  spaced  " is not "spaced".
        self.assertEqual(len(_by(plan, "create")), 1)
        app.refresh_from_db()
        self.assertEqual(app.attributes["app_id"], "  spaced  ")

    def test_numeric_identity_matches_type_strictly(self):
        self.attribute(self.app_type, "Serial", "serial", "number")
        obj = self.make_app("Payroll", serial=1001)

        plan = self.plan(
            [["Serial", "Name"], ["1001", "Payroll v2"]],
            {"column": 0, "field": "attribute.serial", "match": True}, self.NAME,
        )

        self.assertEqual({change.target_id for change in plan.changes}, {obj.id})

    def test_an_unreadable_identity_value_is_blocking(self):
        self.attribute(self.app_type, "Serial", "serial", "number")

        plan = self.plan(
            [["Serial", "Name"], ["abc", "X"]],
            {"column": 0, "field": "attribute.serial", "match": True}, self.NAME,
        )

        self.assertEqual(plan.problems[0].code, "invalid_identity_value")

    def test_id_and_attribute_that_agree_are_accepted(self):
        app = self.make_app("Payroll", "A1")

        plan = self.plan(
            [["ID", "App ID", "Name"], [str(app.id), "A1", "Payroll v2"]],
            {"column": 0, "field": "identity.id"},
            {"column": 1, "field": "attribute.app_id", "match": True},
            {"column": 2, "field": "field.name"},
        )

        self.assertFalse(plan.blocked)
        self.assertEqual(len(plan.changes), 1)

    def test_id_and_attribute_identifying_different_objects_is_a_mismatch(self):
        one = self.make_app("One", "A1")
        self.make_app("Two", "A2")

        plan = self.plan(
            [["ID", "App ID", "Name"], [str(one.id), "A2", "X"]],
            {"column": 0, "field": "identity.id"},
            {"column": 1, "field": "attribute.app_id", "match": True},
            {"column": 2, "field": "field.name"},
        )

        self.assertEqual(plan.problems[0].code, "identity_mismatch")

    # -- the match attribute is never updated on an existing object -------------------

    def test_match_attribute_is_never_updated_on_a_matched_object(self):
        self.make_app("Payroll", "A1")

        plan = self.plan([["App ID", "Name"], ["A1", "Payroll v2"]], self.MATCH, self.NAME)

        self.assertNotIn("attributes.app_id", {change.after["field"] for change in plan.changes})

    def test_match_attribute_is_not_cleared_by_a_blank_cell_on_an_id_resolved_object(self):
        app = self.make_app("Payroll", "A1")

        plan = self.plan(
            [["ID", "App ID", "Name"], [str(app.id), "", "Payroll v2"]],
            {"column": 0, "field": "identity.id"},
            {"column": 1, "field": "attribute.app_id", "match": True},
            {"column": 2, "field": "field.name"},
        )

        self.assertEqual({change.after["field"] for change in plan.changes}, {"name"})

    def test_match_attribute_is_written_on_create(self):
        plan = self.plan([["App ID", "Name"], ["A9", "New"]], self.MATCH, self.NAME)

        self.assertEqual(plan.changes[0].after["attributes"], {"app_id": "A9"})

    # -- mapping and target validation -------------------------------------------------

    def test_object_key_is_not_a_mappable_field(self):
        source = self.stage([["Key", "Name"], ["K1", "X"]])

        with self.assertRaises(MappingError):
            preview_import(
                self.model, source,
                self.object_mapping({"column": 0, "field": "identity.key"}, self.NAME),
            )

    def test_an_unknown_attribute_is_rejected(self):
        source = self.stage([["A", "B"], ["1", "2"]])

        with self.assertRaises(MappingError):
            preview_import(
                self.model, source,
                self.object_mapping({"column": 0, "field": "attribute.nope"}, self.NAME),
            )

    def test_an_inactive_attribute_is_rejected(self):
        AttributeDefinitionInactive = self.attribute(self.app_type, "Old", "old", "text", is_active=False)
        source = self.stage([["A", "B"], ["1", "2"]])

        with self.assertRaises(MappingError):
            preview_import(
                self.model, source,
                self.object_mapping({"column": 0, "field": "attribute.old"}, self.NAME),
            )

    def test_a_type_from_another_model_is_not_found(self):
        source = self.stage([["A", "B"], ["1", "2"]])

        with self.assertRaises(TargetError):
            preview_import(
                self.model, source,
                self.object_mapping(self.NAME, type_id=self.other_app_type.id),
            )

    def test_a_missing_column_is_rejected(self):
        source = self.stage([["A", "B"], ["1", "2"]])

        with self.assertRaises(MappingError):
            preview_import(
                self.model, source, self.object_mapping({"column": 5, "field": "field.name"})
            )

    def test_a_boolean_attribute_cannot_be_the_match_field(self):
        source = self.stage([["A", "B"], ["1", "2"]])

        with self.assertRaises(MappingError):
            preview_import(
                self.model, source,
                self.object_mapping({"column": 0, "field": "attribute.live", "match": True}, self.NAME),
            )

    def test_one_column_and_one_field_cannot_be_mapped_twice(self):
        source = self.stage([["A", "B"], ["1", "2"]])

        for columns in (
            ({"column": 0, "field": "field.name"}, {"column": 0, "field": "attribute.owner"}),
            ({"column": 0, "field": "field.name"}, {"column": 1, "field": "field.name"}),
        ):
            with self.assertRaises(MappingError):
                preview_import(self.model, source, self.object_mapping(*columns))

    def test_the_mapping_is_canonical_and_round_trips(self):
        from ingestion.services.mapping import ImportMapping
        from ingestion.services.targets import resolve_target

        target = resolve_target(self.model, "object", self.app_type.id)
        payload = self.object_mapping(
            {"column": 1, "field": "field.name"}, {"column": 0, "field": "attribute.app_id", "match": True}
        )

        mapping = ImportMapping.from_json(payload, target, column_count=2)

        self.assertEqual([c.column for c in mapping.columns], [0, 1])
        again = ImportMapping.from_json(mapping.to_json(), target, column_count=2)
        self.assertEqual(again, mapping)
        self.assertEqual(again.to_json(), mapping.to_json())
