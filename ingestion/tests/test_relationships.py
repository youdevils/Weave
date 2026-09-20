from ingestion.services.errors import MappingError
from ingestion.services.proposals import preview_import
from ingestion.tests.base import ImportTestCase
from model.models.relationship import Relationship


class RelationshipImportTests(ImportTestCase):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.a = cls.make_app_cls("Alpha", "A")
        cls.b = cls.make_app_cls("Beta", "B")
        cls.c = cls.make_app_cls("Gamma", "C")

    @classmethod
    def make_app_cls(cls, name, app_id):
        from model.models.object import Object

        return Object.objects.create(
            model=cls.model, object_type=cls.app_type, name=name, attributes={"app_id": app_id}
        )

    def plan(self, rows, *columns):
        source = self.stage(rows, "rels.csv")
        return preview_import(self.model, source, self.relationship_mapping(*columns))

    def endpoints(self):
        return (
            self.by_app_id(0, "endpoint.subject"),
            self.by_app_id(1, "endpoint.object"),
        )

    # -- CREATE -----------------------------------------------------------------

    def test_a_new_pair_creates_a_directed_relationship(self):
        plan = self.plan([["From", "To"], ["A", "B"]], *self.endpoints())

        (change,) = plan.changes
        self.assertEqual(change.operation, "create")
        self.assertEqual(change.target_type, "Relationship")
        self.assertEqual(change.parent_type, "RelationshipType")
        self.assertEqual(change.parent_id, self.uses.id)
        self.assertEqual(
            change.after,
            {"subject_id": str(self.a.id), "object_id": str(self.b.id), "is_active": True, "attributes": {}},
        )
        self.assertFalse(Relationship.objects.exists())

    def test_relationship_attributes_are_carried(self):
        plan = self.plan(
            [["From", "To", "Since"], ["A", "B", "2024-01-01"]],
            *self.endpoints(), {"column": 2, "field": "attribute.since"},
        )

        self.assertEqual(plan.changes[0].after["attributes"], {"since": "2024-01-01"})

    def test_endpoints_can_be_given_by_weave_object_id(self):
        plan = self.plan(
            [["From", "To"], [str(self.a.id), str(self.b.id)]],
            {"column": 0, "field": "endpoint.subject", "by": "id"},
            {"column": 1, "field": "endpoint.object", "by": "id"},
        )

        self.assertEqual(plan.changes[0].after["subject_id"], str(self.a.id))

    # -- direction ----------------------------------------------------------------

    def test_direction_is_part_of_identity(self):
        self.make_uses(self.a, self.b)

        plan = self.plan([["From", "To"], ["B", "A"]], *self.endpoints())

        self.assertEqual([c.operation for c in plan.changes], ["create"])
        self.assertEqual(plan.changes[0].after["subject_id"], str(self.b.id))

    def test_the_same_direction_matches_the_existing_relationship(self):
        existing = self.make_uses(self.a, self.b, since="2020-01-01")

        plan = self.plan(
            [["From", "To", "Since"], ["A", "B", "2024-01-01"]],
            *self.endpoints(), {"column": 2, "field": "attribute.since"},
        )

        (change,) = plan.changes
        self.assertEqual(change.operation, "update")
        self.assertEqual(change.target_id, existing.id)
        self.assertEqual(change.before, {"field": "attributes.since", "value": "2020-01-01"})
        self.assertEqual(change.after, {"field": "attributes.since", "value": "2024-01-01"})

    def test_reversed_duplicate_rows_are_two_distinct_relationships(self):
        plan = self.plan([["From", "To"], ["A", "B"], ["B", "A"]], *self.endpoints())

        self.assertEqual(plan.summary.creates, 2)
        self.assertEqual(plan.summary.duplicate_identities, 0)

    # -- UPDATE / NO-OP -------------------------------------------------------------

    def test_unchanged_relationship_is_a_no_op(self):
        self.make_uses(self.a, self.b, since="2024-01-01")

        plan = self.plan(
            [["From", "To", "Since"], ["A", "B", "2024-01-01"]],
            *self.endpoints(), {"column": 2, "field": "attribute.since"},
        )

        self.assertEqual(plan.changes, [])
        self.assertEqual(plan.summary.no_ops, 1)

    def test_an_inactive_existing_relationship_still_matches(self):
        existing = self.make_uses(self.a, self.b)
        Relationship.objects.filter(pk=existing.pk).update(is_active=False)

        plan = self.plan(
            [["From", "To", "Active"], ["A", "B", "yes"]],
            *self.endpoints(), {"column": 2, "field": "field.is_active"},
        )

        (change,) = plan.changes
        self.assertEqual(change.operation, "update")
        self.assertEqual(change.after, {"field": "is_active", "value": True})

    def test_blank_relationship_attribute_on_update_clears_it(self):
        self.make_uses(self.a, self.b, since="2020-01-01")

        plan = self.plan(
            [["From", "To", "Since"], ["A", "B", ""]],
            *self.endpoints(), {"column": 2, "field": "attribute.since"},
        )

        self.assertEqual(plan.changes[0].after, {"field": "attributes.since", "value": None})

    def test_endpoints_are_never_changed_on_update(self):
        self.make_uses(self.a, self.b)

        plan = self.plan(
            [["From", "To", "Since"], ["A", "B", "2024-01-01"]],
            *self.endpoints(), {"column": 2, "field": "attribute.since"},
        )

        self.assertEqual({c.after["field"] for c in plan.changes}, {"attributes.since"})

    # -- unresolved / ambiguous -------------------------------------------------------

    def test_an_unresolved_endpoint_blocks(self):
        plan = self.plan([["From", "To"], ["A", "NOPE"]], *self.endpoints())

        self.assertTrue(plan.blocked)
        self.assertEqual(plan.problems[0].code, "unresolved_endpoint")
        self.assertEqual(plan.problems[0].row, 2)
        self.assertEqual(plan.changes, [])

    def test_a_blank_endpoint_blocks(self):
        plan = self.plan([["From", "To"], ["A", ""]], *self.endpoints())

        self.assertEqual(plan.problems[0].code, "missing_endpoint")

    def test_an_ambiguous_endpoint_blocks(self):
        self.make_app("Dup", "B")

        plan = self.plan([["From", "To"], ["A", "B"]], *self.endpoints())

        self.assertEqual(plan.problems[0].code, "ambiguous_endpoint")

    def test_an_endpoint_id_from_another_model_reads_as_unresolved(self):
        from model.models.object import Object

        foreign = Object.objects.create(model=self.other_model, object_type=self.other_app_type, name="F")

        plan = self.plan(
            [["From", "To"], [str(self.a.id), str(foreign.id)]],
            {"column": 0, "field": "endpoint.subject", "by": "id"},
            {"column": 1, "field": "endpoint.object", "by": "id"},
        )

        self.assertEqual(plan.problems[0].code, "unresolved_endpoint")

    def test_a_malformed_endpoint_id_blocks(self):
        plan = self.plan(
            [["From", "To"], ["x", str(self.b.id)]],
            {"column": 0, "field": "endpoint.subject", "by": "id"},
            {"column": 1, "field": "endpoint.object", "by": "id"},
        )

        self.assertEqual(plan.problems[0].code, "invalid_endpoint_id")

    def test_several_existing_relationships_for_one_pair_are_ambiguous(self):
        self.make_uses(self.a, self.b)
        self.make_uses(self.a, self.b)

        plan = self.plan([["From", "To"], ["A", "B"]], *self.endpoints())

        self.assertEqual(plan.problems[0].code, "ambiguous_relationship")

    def test_every_problem_is_reported_not_just_the_first(self):
        plan = self.plan(
            [["From", "To"], ["NOPE", "B"], ["A", "NOPE"], ["A", "B"]], *self.endpoints()
        )

        self.assertEqual([p.row for p in plan.problems], [2, 3])

    # -- Weave Relationship ID ----------------------------------------------------------

    def test_a_relationship_id_identifies_the_relationship_without_endpoints(self):
        existing = self.make_uses(self.a, self.b)

        plan = self.plan(
            [["ID", "Since"], [str(existing.id), "2024-01-01"]],
            {"column": 0, "field": "identity.id"}, {"column": 1, "field": "attribute.since"},
        )

        self.assertEqual(plan.changes[0].target_id, existing.id)

    def test_id_with_agreeing_endpoints_is_only_cross_checked(self):
        existing = self.make_uses(self.a, self.b)

        plan = self.plan(
            [["ID", "From", "To", "Since"], [str(existing.id), "A", "B", "2024-01-01"]],
            {"column": 0, "field": "identity.id"},
            self.by_app_id(1, "endpoint.subject"), self.by_app_id(2, "endpoint.object"),
            {"column": 3, "field": "attribute.since"},
        )

        self.assertFalse(plan.blocked)
        self.assertEqual({c.after["field"] for c in plan.changes}, {"attributes.since"})

    def test_id_with_disagreeing_endpoints_is_a_mismatch_and_never_rewires(self):
        existing = self.make_uses(self.a, self.b)

        plan = self.plan(
            [["ID", "From", "To"], [str(existing.id), "A", "C"]],
            {"column": 0, "field": "identity.id"},
            self.by_app_id(1, "endpoint.subject"), self.by_app_id(2, "endpoint.object"),
        )

        self.assertEqual(plan.problems[0].code, "identity_mismatch")
        self.assertEqual(plan.changes, [])

    def test_an_unknown_relationship_id_blocks(self):
        plan = self.plan(
            [["ID", "Since"], [self.new_id(), "2024-01-01"]],
            {"column": 0, "field": "identity.id"}, {"column": 1, "field": "attribute.since"},
        )

        self.assertEqual(plan.problems[0].code, "unresolved_identity")

    def test_a_relationship_id_of_another_type_blocks(self):
        from model.models.relationship_type import RelationshipType

        other = RelationshipType.objects.create(model=self.model, name="Owns", key="owns")
        rel = Relationship.objects.create(
            model=self.model, relationship_type=other, subject=self.a, object=self.b
        )

        plan = self.plan(
            [["ID", "Since"], [str(rel.id), "2024-01-01"]],
            {"column": 0, "field": "identity.id"}, {"column": 1, "field": "attribute.since"},
        )

        self.assertEqual(plan.problems[0].code, "wrong_relationship_type")

    # -- mapping rules ---------------------------------------------------------------------

    def test_without_an_id_both_endpoints_are_required(self):
        source = self.stage([["From", "To"], ["A", "B"]], "rels.csv")

        with self.assertRaises(MappingError):
            preview_import(self.model, source, self.relationship_mapping(self.by_app_id(0, "endpoint.subject")))

    def test_an_id_plus_one_endpoint_is_an_invalid_mapping(self):
        source = self.stage([["ID", "From"], [self.new_id(), "A"]], "rels.csv")

        with self.assertRaises(MappingError):
            preview_import(
                self.model, source,
                self.relationship_mapping(
                    {"column": 0, "field": "identity.id"}, self.by_app_id(1, "endpoint.subject")
                ),
            )

    def test_an_attribute_endpoint_needs_an_object_type(self):
        source = self.stage([["From", "To"], ["A", "B"]], "rels.csv")

        with self.assertRaises(MappingError):
            preview_import(
                self.model, source,
                self.relationship_mapping(
                    {"column": 0, "field": "endpoint.subject", "by": "attribute:app_id"},
                    {"column": 1, "field": "endpoint.object", "by": "id"},
                ),
            )

    def test_only_object_imports_can_match_on_an_attribute(self):
        source = self.stage([["From", "To", "Since"], ["A", "B", "x"]], "rels.csv")

        with self.assertRaises(MappingError):
            preview_import(
                self.model, source,
                self.relationship_mapping(
                    *self.endpoints(), {"column": 2, "field": "attribute.since", "match": True}
                ),
            )

    def test_the_relationship_rules_are_not_the_importers_concern(self):
        # Person -> Person is not permitted by the `uses` rule; the plan still
        # builds the CREATE and leaves the verdict to the Proposal validator.
        from model.models.object import Object

        Object.objects.create(model=self.model, object_type=self.person_type, name="Ann", attributes={})
        person_id_attr = self.attribute(self.person_type, "Badge", "badge", "text")
        Object.objects.filter(name="Ann").update(attributes={"badge": "P1"})

        plan = self.plan(
            [["From", "To"], ["P1", "P1"]],
            {"column": 0, "field": "endpoint.subject", "by": "attribute:badge",
             "object_type_id": str(self.person_type.id)},
            {"column": 1, "field": "endpoint.object", "by": "attribute:badge",
             "object_type_id": str(self.person_type.id)},
        )

        self.assertFalse(plan.blocked)
        self.assertEqual(plan.changes[0].operation, "create")
