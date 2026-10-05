from django.urls import reverse

from model.models.evidence_reference import EvidenceReference
from model.models.object import Object
from model.models.object_type import ObjectType
from model.models.proposal import Proposal, ProposalChange
from model.models.relationship_type import RelationshipType
from model.services.proposal.proposal import ProposalService
from workspace.models import WorkspaceMember

from ai.services.change_plan import ChangeAction, ChangePlan, EntityRef, EvidenceItem
from ai.services.proposal_compiler import (
    InvalidFieldError,
    compile_and_validate,
    compile_change_plan,
)
from ai.tests.support import AIServiceTestCase, fake_operation


def _existing(id_):
    return EntityRef(kind="existing", id=str(id_))


def _new(token):
    return EntityRef(kind="new", id=token)


class CompileChangePlanTests(AIServiceTestCase):

    def setUp(self):
        self.model = self.make_model()
        self.object_type = self.make_object_type(self.model, key="widget")
        self.object = self.make_object(self.model, self.object_type, name="Widget 1", key="widget_1")
        self.proposal = ProposalService.create_working(
            self.model, self.user, source=Proposal.Source.AI
        )

    def test_compile_create_action_maps_fields_to_single_after_payload(self):
        plan = ChangePlan(
            actions=[
                ChangeAction(
                    operation="create",
                    target_type="Object",
                    target_ref=_new("tmp:1"),
                    parent_ref=_existing(self.object_type.key),
                    fields={"name": "New widget", "description": "", "is_active": True},
                )
            ]
        )

        created = compile_change_plan(model=self.model, user=self.user, change_plan=plan, proposal=self.proposal)

        self.assertEqual(len(created), 1)
        change = created[0]
        self.assertEqual(change.operation, ProposalChange.Operation.CREATE)
        self.assertEqual(change.after["name"], "New widget")
        self.assertEqual(str(change.parent_id), str(self.object_type.id))

    def test_object_type_create_is_stamped_with_the_implied_model_parent(self):
        """
        ObjectType has no parent_ref in the Change Plan schema -- Model
        isn't part of the EntityRef graph, so there's nothing to resolve a
        parent from. But model/views/common_context.py's
        _build_working_object_types only recognises a CREATE as
        proposal-only when parent_type == "Model" (the same literal every
        editor-driven CREATE already stamps), so the compiler must supply
        it itself. A regression here means a compiled AI proposal's
        ObjectTypes silently never appear in the sidebar/editors, even
        though the ProposalChange row is otherwise perfectly valid.
        """
        plan = ChangePlan(
            actions=[
                ChangeAction(
                    operation="create",
                    target_type="ObjectType",
                    target_ref=_new("tmp:1"),
                    fields={"name": "Customer Type"},
                )
            ]
        )

        created = compile_change_plan(model=self.model, user=self.user, change_plan=plan, proposal=self.proposal)

        self.assertEqual(created[0].parent_type, "Model")
        self.assertEqual(created[0].parent_id, self.model.id)

    def test_relationship_type_create_is_stamped_with_the_implied_model_parent(self):
        plan = ChangePlan(
            actions=[
                ChangeAction(
                    operation="create",
                    target_type="RelationshipType",
                    target_ref=_new("tmp:1"),
                    fields={"name": "Connects To"},
                )
            ]
        )

        created = compile_change_plan(model=self.model, user=self.user, change_plan=plan, proposal=self.proposal)

        self.assertEqual(created[0].parent_type, "Model")
        self.assertEqual(created[0].parent_id, self.model.id)

    def test_compile_create_action_nests_attribute_prefixed_fields(self):
        """
        An Object's dynamic attributes are set, at CREATE time, via the
        "attributes.<key>" dotted convention in `fields` -- the same
        convention model.services.field_paths already defines for
        field-level attribute UPDATEs -- and ChangeAction.fields_dict()
        must nest them into the single "attributes" dict
        Object.objects.create(**after) expects.
        """
        plan = ChangePlan(
            actions=[
                ChangeAction(
                    operation="create",
                    target_type="Object",
                    target_ref=_new("tmp:1"),
                    parent_ref=_existing(self.object_type.key),
                    fields={"name": "New widget", "attributes.cost": 42.5},
                )
            ]
        )

        created = compile_change_plan(model=self.model, user=self.user, change_plan=plan, proposal=self.proposal)

        self.assertEqual(len(created), 1)
        change = created[0]
        self.assertEqual(change.after["name"], "New widget")
        self.assertEqual(change.after["attributes"], {"cost": 42.5})

    def test_compile_update_action_fans_out_to_one_spec_per_field(self):
        plan = ChangePlan(
            actions=[
                ChangeAction(
                    operation="update",
                    target_type="Object",
                    target_ref=_existing(f"widget:{self.object.key}"),
                    fields={"name": "Renamed", "description": "New description"},
                )
            ]
        )

        created = compile_change_plan(model=self.model, user=self.user, change_plan=plan, proposal=self.proposal)

        self.assertEqual(len(created), 2)
        fields = {c.after["field"] for c in created}
        self.assertEqual(fields, {"name", "description"})

    def test_compile_update_action_populates_before_from_current_canonical_value(self):
        plan = ChangePlan(
            actions=[
                ChangeAction(
                    operation="update",
                    target_type="Object",
                    target_ref=_existing(f"widget:{self.object.key}"),
                    fields={"name": "Renamed"},
                )
            ]
        )

        created = compile_change_plan(model=self.model, user=self.user, change_plan=plan, proposal=self.proposal)

        self.assertEqual(created[0].before, {"field": "name", "value": "Widget 1"})

    def test_compile_new_entity_referenced_by_later_action_in_same_plan(self):
        relationship_type = self.make_relationship_type(self.model, key="connects_to")
        plan = ChangePlan(
            actions=[
                ChangeAction(
                    operation="create",
                    target_type="Object",
                    target_ref=_new("tmp:new_obj"),
                    parent_ref=_existing(self.object_type.key),
                    fields={"name": "New widget"},
                ),
                ChangeAction(
                    operation="create",
                    target_type="Relationship",
                    target_ref=_new("tmp:rel"),
                    parent_ref=_existing(relationship_type.key),
                    fields={
                        "subject_id": _existing(f"widget:{self.object.key}").model_dump(),
                        "object_id": _new("tmp:new_obj").model_dump(),
                    },
                ),
            ]
        )

        created = compile_change_plan(model=self.model, user=self.user, change_plan=plan, proposal=self.proposal)

        object_change = next(c for c in created if c.target_type == "Object")
        relationship_change = next(c for c in created if c.target_type == "Relationship")

        self.assertEqual(str(relationship_change.after["object_id"]), str(object_change.target_id))

    def test_rationale_is_attached_as_evidence_reference_note(self):
        plan = ChangePlan(
            actions=[
                ChangeAction(
                    operation="update",
                    target_type="Object",
                    target_ref=_existing(f"widget:{self.object.key}"),
                    fields={"name": "Renamed"},
                    rationale="The intent asked for a rename.",
                )
            ]
        )

        created = compile_change_plan(model=self.model, user=self.user, change_plan=plan, proposal=self.proposal)

        evidence = EvidenceReference.objects.filter(change=created[0])
        self.assertEqual(evidence.count(), 1)
        self.assertEqual(evidence.first().note, "The intent asked for a rename.")
        self.assertEqual(evidence.first().source, "AI")

    def test_rationale_and_explicit_evidence_items_both_attached(self):
        plan = ChangePlan(
            actions=[
                ChangeAction(
                    operation="update",
                    target_type="Object",
                    target_ref=_existing(f"widget:{self.object.key}"),
                    fields={"name": "Renamed"},
                    rationale="Why I did this.",
                    evidence=[EvidenceItem(source="doc.pdf", locator="p.3", note="Source context.")],
                )
            ]
        )

        created = compile_change_plan(model=self.model, user=self.user, change_plan=plan, proposal=self.proposal)

        self.assertEqual(EvidenceReference.objects.filter(change=created[0]).count(), 2)

    def test_compile_never_calls_submit_proposal_stays_working(self):
        plan = ChangePlan(
            actions=[
                ChangeAction(
                    operation="update",
                    target_type="Object",
                    target_ref=_existing(f"widget:{self.object.key}"),
                    fields={"name": "Renamed"},
                )
            ]
        )

        compile_change_plan(model=self.model, user=self.user, change_plan=plan, proposal=self.proposal)

        self.proposal.refresh_from_db()
        self.assertEqual(self.proposal.status, Proposal.Status.WORKING)

    def test_existing_attribute_definition_is_resolved_by_its_composite_definition_ref(self):
        """
        End-to-end proof that the "attribute_definition" domain (a
        previously-"unverifiable" Phase 1 boundary, now a real, checked
        domain) resolves an UPDATE targeting an *existing* AttributeDefinition
        by its "{ObjectType|RelationshipType}:{parent_key}:{key}" composite
        ref, exactly as ai.services.ontology_context renders it.
        """
        attribute_definition = self.make_attribute_definition(
            object_type=self.object_type, key="capacity", name="Capacity", data_type="number"
        )
        plan = ChangePlan(
            actions=[
                ChangeAction(
                    operation="update",
                    target_type="AttributeDefinition",
                    target_ref=_existing(f"ObjectType:{self.object_type.key}:capacity"),
                    fields={"name": "Max Capacity"},
                )
            ]
        )

        created = compile_change_plan(model=self.model, user=self.user, change_plan=plan, proposal=self.proposal)

        self.assertEqual(len(created), 1)
        self.assertEqual(str(created[0].target_id), str(attribute_definition.id))
        self.assertEqual(created[0].after, {"field": "name", "value": "Max Capacity"})


class KeyFallbackCompileTests(AIServiceTestCase):
    """
    A CREATE ObjectType/RelationshipType action's `key` is always derived
    from its name -- see ai.services.proposal_compiler._assign_key, which
    wraps model.services.keys and never trusts an AI-supplied key. UPDATE
    actions are rejected outright (key is never update-legal); other
    target_types are untouched.
    """

    def setUp(self):
        self.model = self.make_model()
        self.proposal = ProposalService.create_working(
            self.model, self.user, source=Proposal.Source.AI
        )

    def _create_object_type(self, name, key=None):
        fields = {"name": name}
        if key is not None:
            fields["key"] = key
        return ChangeAction(
            operation="create",
            target_type="ObjectType",
            target_ref=_new("tmp:1"),
            fields=fields,
        )

    def test_object_type_create_missing_key_is_derived_from_name(self):
        plan = ChangePlan(actions=[self._create_object_type("Customer Type")])

        created = compile_change_plan(model=self.model, user=self.user, change_plan=plan, proposal=self.proposal)

        self.assertEqual(created[0].after["key"], "customer_type")

    def test_object_type_create_blank_key_is_derived_from_name(self):
        for blank in ("", "   "):
            with self.subTest(blank=repr(blank)):
                # A fresh proposal per iteration: generate_key also checks
                # keys already claimed by earlier CREATEs recorded in the
                # SAME proposal, so reusing one across iterations would
                # make the second "Customer Type" collide with the first.
                proposal = ProposalService.create_working(
                    self.model, self.user, source=Proposal.Source.AI
                )
                plan = ChangePlan(actions=[self._create_object_type("Customer Type", key=blank)])

                created = compile_change_plan(
                    model=self.model, user=self.user, change_plan=plan, proposal=proposal
                )

                self.assertEqual(created[0].after["key"], "customer_type")

    def test_relationship_type_create_missing_key_is_derived_from_name(self):
        plan = ChangePlan(
            actions=[
                ChangeAction(
                    operation="create",
                    target_type="RelationshipType",
                    target_ref=_new("tmp:1"),
                    fields={"name": "Connects To"},
                )
            ]
        )

        created = compile_change_plan(model=self.model, user=self.user, change_plan=plan, proposal=self.proposal)

        self.assertEqual(created[0].after["key"], "connects_to")

    def test_explicit_create_key_is_always_overridden(self):
        # Keys are fully automatic: whatever key a Change Plan action
        # supplies is discarded and derived from the name instead, the
        # same as a human-typed key would be.
        plan = ChangePlan(actions=[self._create_object_type("Customer Type", key="custom_key")])

        created = compile_change_plan(model=self.model, user=self.user, change_plan=plan, proposal=self.proposal)

        self.assertEqual(created[0].after["key"], "customer_type")

    def test_two_same_named_creates_in_one_plan_get_distinct_keys(self):
        plan = ChangePlan(
            actions=[
                self._create_object_type("Customer Type"),
                ChangeAction(
                    operation="create",
                    target_type="ObjectType",
                    target_ref=_new("tmp:2"),
                    fields={"name": "Customer Type"},
                ),
            ]
        )

        created = compile_change_plan(model=self.model, user=self.user, change_plan=plan, proposal=self.proposal)

        self.assertEqual({c.after["key"] for c in created}, {"customer_type", "customer_type_2"})

    def test_derived_key_colliding_with_existing_db_key_gets_suffixed(self):
        ObjectType.objects.create(model=self.model, name="Existing", key="customer_type")
        plan = ChangePlan(actions=[self._create_object_type("Customer Type")])

        created = compile_change_plan(model=self.model, user=self.user, change_plan=plan, proposal=self.proposal)

        self.assertEqual(created[0].after["key"], "customer_type_2")

    def test_update_of_key_is_rejected_as_an_illegal_field(self):
        # Keys never change after creation -- entity_fields.illegal_fields
        # excludes "key" from the update-legal set, so this is caught here,
        # the same InvalidFieldError path as any other unsettable field.
        object_type = self.make_object_type(self.model, key="widget")
        plan = ChangePlan(
            actions=[
                ChangeAction(
                    operation="update",
                    target_type="ObjectType",
                    target_ref=_existing(object_type.key),
                    fields={"key": "renamed"},
                )
            ]
        )

        with self.assertRaises(InvalidFieldError) as ctx:
            compile_change_plan(model=self.model, user=self.user, change_plan=plan, proposal=self.proposal)

        self.assertEqual(ctx.exception.field_names, ["key"])

    def test_non_key_bearing_create_types_unaffected(self):
        # RelationshipTypeRule has no key of its own -- unlike Object (also
        # a CREATE target here, but key-bearing since Phase B).
        object_type = self.make_object_type(self.model, key="widget")
        relationship_type = self.make_relationship_type(self.model, key="depends_on")
        plan = ChangePlan(
            actions=[
                ChangeAction(
                    operation="create",
                    target_type="RelationshipTypeRule",
                    target_ref=_new("tmp:1"),
                    parent_ref=_existing(relationship_type.key),
                    fields={
                        "subject_type_id": str(object_type.id),
                        "object_type_id": str(object_type.id),
                    },
                )
            ]
        )

        created = compile_change_plan(model=self.model, user=self.user, change_plan=plan, proposal=self.proposal)

        self.assertNotIn("key", created[0].after)

    def test_object_create_key_is_derived_from_name(self):
        # Object became key-bearing in Phase B -- the same fallback path
        # as ObjectType/RelationshipType/AttributeDefinition.
        object_type = self.make_object_type(self.model, key="widget")
        plan = ChangePlan(
            actions=[
                ChangeAction(
                    operation="create",
                    target_type="Object",
                    target_ref=_new("tmp:1"),
                    parent_ref=_existing(object_type.key),
                    fields={"name": "Widget 1"},
                )
            ]
        )

        created = compile_change_plan(model=self.model, user=self.user, change_plan=plan, proposal=self.proposal)

        self.assertEqual(created[0].after["key"], "widget_1")

    def test_object_type_create_unsluggable_name_gets_the_fallback_key(self):
        # Creation must never block just because the name has no
        # sluggable characters -- it falls back to a per-type base word.
        plan = ChangePlan(actions=[self._create_object_type("???")])

        created = compile_change_plan(model=self.model, user=self.user, change_plan=plan, proposal=self.proposal)

        self.assertEqual(created[0].after["key"], "object_type")

    def test_two_unsluggable_creates_in_one_plan_get_distinct_fallback_keys(self):
        plan = ChangePlan(
            actions=[
                self._create_object_type("???"),
                ChangeAction(
                    operation="create",
                    target_type="ObjectType",
                    target_ref=_new("tmp:2"),
                    fields={"name": "???"},
                ),
            ]
        )

        created = compile_change_plan(model=self.model, user=self.user, change_plan=plan, proposal=self.proposal)

        self.assertEqual({c.after["key"] for c in created}, {"object_type", "object_type_2"})


class InvalidFieldCompileTests(AIServiceTestCase):
    """
    A CREATE/UPDATE action supplying a `fields` key that isn't a real,
    settable field for its target_type must be rejected deterministically
    (InvalidFieldError -> ValidationIssue) before it ever reaches
    model_cls.objects.create()/instance.save() -- never a raw Django
    TypeError. See model.services.entity_fields for the legal-field
    registry this reuses.
    """

    def setUp(self):
        self.model = self.make_model()
        self.proposal = ProposalService.create_working(
            self.model, self.user, source=Proposal.Source.AI
        )

    def test_relationship_type_create_with_to_from_raises_invalid_field_error(self):
        plan = ChangePlan(
            actions=[
                ChangeAction(
                    operation="create",
                    target_type="RelationshipType",
                    target_ref=_new("tmp:1"),
                    fields={"name": "Connects To", "to": "x", "from": "y"},
                )
            ]
        )

        with self.assertRaises(InvalidFieldError) as ctx:
            compile_change_plan(model=self.model, user=self.user, change_plan=plan, proposal=self.proposal)

        self.assertEqual(ctx.exception.target_type, "RelationshipType")
        self.assertEqual(sorted(ctx.exception.field_names), ["from", "to"])

    def test_object_type_create_with_illegal_field_raises(self):
        plan = ChangePlan(
            actions=[
                ChangeAction(
                    operation="create",
                    target_type="ObjectType",
                    target_ref=_new("tmp:1"),
                    fields={"name": "Customer", "bogus": "x"},
                )
            ]
        )

        with self.assertRaises(InvalidFieldError) as ctx:
            compile_change_plan(model=self.model, user=self.user, change_plan=plan, proposal=self.proposal)

        self.assertEqual(ctx.exception.target_type, "ObjectType")
        self.assertEqual(ctx.exception.field_names, ["bogus"])

    def test_relationship_type_rule_create_with_correct_fields_compiles_successfully(self):
        relationship_type = self.make_relationship_type(self.model, key="connects_to")
        subject_type = self.make_object_type(self.model, key="widget")
        object_type = self.make_object_type(self.model, key="gadget", name="Gadget")

        plan = ChangePlan(
            actions=[
                ChangeAction(
                    operation="create",
                    target_type="RelationshipTypeRule",
                    target_ref=_new("tmp:rule"),
                    parent_ref=_existing(relationship_type.key),
                    fields={
                        "subject_type_id": _existing(subject_type.key).model_dump(),
                        "object_type_id": _existing(object_type.key).model_dump(),
                        "subject_minimum": 0,
                        "subject_maximum": 1,
                        "object_minimum": 0,
                        "object_maximum": None,
                    },
                )
            ]
        )

        created = compile_change_plan(model=self.model, user=self.user, change_plan=plan, proposal=self.proposal)

        self.assertEqual(len(created), 1)
        self.assertEqual(created[0].target_type, "RelationshipTypeRule")
        self.assertEqual(created[0].after["subject_minimum"], 0)
        self.assertEqual(created[0].after["subject_maximum"], 1)
        self.assertIsInstance(created[0].after["subject_minimum"], int)
        self.assertIsInstance(created[0].after["subject_maximum"], int)

    def test_relationship_type_rule_cardinality_values_stay_integers(self):
        """Regression: AI-supplied cardinality values (e.g. 1, 2, 8, 10) must
        survive compilation as real ints, not floats -- see
        ai.services.change_plan.FieldValue.number_value."""
        relationship_type = self.make_relationship_type(self.model, key="connects_to")
        subject_type = self.make_object_type(self.model, key="widget")
        object_type = self.make_object_type(self.model, key="gadget", name="Gadget")

        for value in (0, 1, 2, 8, 10):
            with self.subTest(value=value):
                plan = ChangePlan(
                    actions=[
                        ChangeAction(
                            operation="create",
                            target_type="RelationshipTypeRule",
                            target_ref=_new(f"tmp:rule-{value}"),
                            parent_ref=_existing(relationship_type.key),
                            fields={
                                "subject_type_id": _existing(subject_type.key).model_dump(),
                                "object_type_id": _existing(object_type.key).model_dump(),
                                "subject_minimum": value,
                                "subject_maximum": value,
                                "object_minimum": value,
                                "object_maximum": value,
                            },
                        )
                    ]
                )

                created = compile_change_plan(
                    model=self.model, user=self.user, change_plan=plan, proposal=self.proposal
                )

                after = created[0].after
                for key in ("subject_minimum", "subject_maximum", "object_minimum", "object_maximum"):
                    self.assertEqual(after[key], value)
                    self.assertIsInstance(after[key], int)

    def test_relationship_type_rule_create_with_ai_facing_ref_aliases_compiles_to_internal_keys(self):
        """The AI-facing `_ref` names are purely a contract-level rename --
        compile_change_plan must still produce the same internal `_id`
        keys on the resulting ProposalChange, unchanged in intent."""
        relationship_type = self.make_relationship_type(self.model, key="connects_to")
        subject_type = self.make_object_type(self.model, key="widget")
        object_type = self.make_object_type(self.model, key="gadget", name="Gadget")

        plan = ChangePlan(
            actions=[
                ChangeAction(
                    operation="create",
                    target_type="RelationshipTypeRule",
                    target_ref=_new("tmp:rule"),
                    parent_ref=_existing(relationship_type.key),
                    fields={
                        "subject_type_ref": _existing(subject_type.key).model_dump(),
                        "object_type_ref": _existing(object_type.key).model_dump(),
                        "subject_minimum": 0,
                        "subject_maximum": 1,
                        "object_minimum": 0,
                        "object_maximum": None,
                    },
                )
            ]
        )

        created = compile_change_plan(model=self.model, user=self.user, change_plan=plan, proposal=self.proposal)

        self.assertEqual(created[0].after["subject_type_id"], str(subject_type.id))
        self.assertEqual(created[0].after["object_type_id"], str(object_type.id))
        self.assertNotIn("subject_type_ref", created[0].after)
        self.assertNotIn("object_type_ref", created[0].after)

    def test_new_object_type_created_in_plan_can_be_referenced_by_a_later_action_in_the_same_plan(self):
        """The symbolic-reference mechanism: a 'new' token defined by one
        create action resolves to the same real id everywhere else it's
        referenced within the same Change Plan -- here, a later Object
        create uses it as parent_ref."""
        plan = ChangePlan(
            actions=[
                ChangeAction(
                    operation="create",
                    target_type="ObjectType",
                    target_ref=_new("ot1"),
                    fields={"name": "Customer"},
                ),
                ChangeAction(
                    operation="create",
                    target_type="Object",
                    target_ref=_new("obj1"),
                    parent_ref=_new("ot1"),
                    fields={"name": "Acme Inc."},
                ),
            ]
        )

        created = compile_change_plan(model=self.model, user=self.user, change_plan=plan, proposal=self.proposal)

        self.assertEqual(len(created), 2)
        object_type_change, object_change = created
        self.assertEqual(object_type_change.target_type, "ObjectType")
        self.assertEqual(object_change.target_type, "Object")
        self.assertEqual(str(object_change.parent_id), str(object_type_change.target_id))

    def test_update_action_with_illegal_field_raises_collecting_all_bad_keys(self):
        object_type = self.make_object_type(self.model, key="widget")
        plan = ChangePlan(
            actions=[
                ChangeAction(
                    operation="update",
                    target_type="ObjectType",
                    target_ref=_existing(object_type.key),
                    fields={"to": "x", "from": "y"},
                )
            ]
        )

        with self.assertRaises(InvalidFieldError) as ctx:
            compile_change_plan(model=self.model, user=self.user, change_plan=plan, proposal=self.proposal)

        self.assertEqual(sorted(ctx.exception.field_names), ["from", "to"])

    def test_update_action_with_legal_field_is_unaffected(self):
        object_type = self.make_object_type(self.model, key="widget")
        plan = ChangePlan(
            actions=[
                ChangeAction(
                    operation="update",
                    target_type="ObjectType",
                    target_ref=_existing(object_type.key),
                    fields={"name": "Renamed"},
                )
            ]
        )

        created = compile_change_plan(model=self.model, user=self.user, change_plan=plan, proposal=self.proposal)

        self.assertEqual(created[0].after, {"field": "name", "value": "Renamed"})

    def test_object_create_with_attribute_prefixed_field_is_not_flagged(self):
        object_type = self.make_object_type(self.model, key="widget")
        plan = ChangePlan(
            actions=[
                ChangeAction(
                    operation="create",
                    target_type="Object",
                    target_ref=_new("tmp:1"),
                    parent_ref=_existing(object_type.key),
                    fields={"name": "Widget 1", "attributes.cost": 42.5},
                )
            ]
        )

        created = compile_change_plan(model=self.model, user=self.user, change_plan=plan, proposal=self.proposal)

        self.assertEqual(created[0].after["attributes"], {"cost": 42.5})


class CompileAndValidateTests(AIServiceTestCase):

    def setUp(self):
        self.model = self.make_model()
        self.object_type = self.make_object_type(self.model, key="widget")
        self.operation = fake_operation()

    def _valid_plan(self, summary="Create a widget."):
        return ChangePlan(
            summary=summary,
            actions=[
                ChangeAction(
                    operation="create",
                    target_type="Object",
                    target_ref=_new("tmp:1"),
                    parent_ref=_existing(self.object_type.key),
                    fields={"name": "New widget"},
                )
            ],
        )

    def _invalid_plan(self):
        # An empty name fails validate_object_builtin_fields's pre-check
        # inside _apply_changes -- reported as a ValidationIssue, not a
        # raised exception, so apply_and_validate returns cleanly with
        # issues for compile_and_validate to roll back on.
        return ChangePlan(
            summary="",
            actions=[
                ChangeAction(
                    operation="create",
                    target_type="Object",
                    target_ref=_new("tmp:1"),
                    parent_ref=_existing(self.object_type.key),
                    fields={"name": ""},
                )
            ],
        )

    def test_compile_and_validate_commits_exactly_one_proposal_on_success(self):
        result = compile_and_validate(
            model=self.model, user=self.user, operation=self.operation, change_plan=self._valid_plan()
        )

        self.assertIsNotNone(result.proposal)
        self.assertEqual(result.issues, [])
        self.assertEqual(Proposal.objects.filter(id=result.proposal.id).count(), 1)
        self.assertTrue(result.proposal.changes.exists())

    def test_change_plan_summary_maps_to_proposal_summary_field(self):
        result = compile_and_validate(
            model=self.model,
            user=self.user,
            operation=self.operation,
            change_plan=self._valid_plan(summary="Because the intent asked for it."),
        )

        self.assertEqual(result.proposal.summary, "Because the intent asked for it.")

    def test_successful_attempt_commits_proposal_but_rolls_back_speculative_canonical_writes(self):
        revision_before = self.model.revision

        result = compile_and_validate(
            model=self.model, user=self.user, operation=self.operation, change_plan=self._valid_plan()
        )

        self.assertIsNotNone(result.proposal)
        self.model.refresh_from_db()
        self.assertEqual(self.model.revision, revision_before)
        self.assertEqual(Object.objects.filter(model=self.model).count(), 0)

    def test_failed_attempt_leaves_no_durable_trace(self):
        proposal_count_before = Proposal.objects.count()
        change_count_before = ProposalChange.objects.count()
        evidence_count_before = EvidenceReference.objects.count()
        object_count_before = Object.objects.count()
        revision_before = self.model.revision

        result = compile_and_validate(
            model=self.model, user=self.user, operation=self.operation, change_plan=self._invalid_plan()
        )

        self.assertIsNone(result.proposal)
        self.assertTrue(result.issues)
        self.assertEqual(Proposal.objects.count(), proposal_count_before)
        self.assertEqual(ProposalChange.objects.count(), change_count_before)
        self.assertEqual(EvidenceReference.objects.count(), evidence_count_before)
        self.assertEqual(Object.objects.filter(model=self.model).count(), object_count_before)
        self.model.refresh_from_db()
        self.assertEqual(self.model.revision, revision_before)

    def _object_type_plan(self, name, key=None):
        fields = {"name": name}
        if key is not None:
            fields["key"] = key
        return ChangePlan(
            actions=[
                ChangeAction(
                    operation="create",
                    target_type="ObjectType",
                    target_ref=_new("tmp:1"),
                    fields=fields,
                )
            ],
        )

    def test_object_type_create_unsluggable_name_compiles_with_the_fallback_key(self):
        # Creation never blocks just because the name has no sluggable
        # characters -- it falls back to a per-type base word instead of
        # raising (see model.services.keys.generate_key).
        result = compile_and_validate(
            model=self.model, user=self.user, operation=self.operation,
            change_plan=self._object_type_plan("???"),
        )

        self.assertIsNotNone(result.proposal)
        self.assertEqual(result.issues, [])
        change = result.proposal.changes.get(target_type="ObjectType")
        self.assertEqual(change.after["key"], "object_type")

    def test_object_type_create_missing_key_compiles_and_persists_end_to_end(self):
        result = compile_and_validate(
            model=self.model, user=self.user, operation=self.operation,
            change_plan=self._object_type_plan("Customer Type"),
        )

        self.assertEqual(result.issues, [])
        self.assertIsNotNone(result.proposal)
        change = result.proposal.changes.get(target_type="ObjectType")
        self.assertEqual(change.after["key"], "customer_type")

    def test_compile_and_validate_returns_clean_issue_for_invalid_field_no_persistence(self):
        """
        End-to-end reproduction of the original crash: a RelationshipType
        CREATE with `to`/`from` must come back as a clean, retryable
        ValidationIssue -- never an uncaught Django TypeError, and never a
        persisted row.
        """
        proposal_count_before = Proposal.objects.count()
        change_count_before = ProposalChange.objects.count()

        plan = ChangePlan(
            actions=[
                ChangeAction(
                    operation="create",
                    target_type="RelationshipType",
                    target_ref=_new("tmp:1"),
                    fields={"name": "Connects To", "to": "x", "from": "y"},
                )
            ]
        )

        result = compile_and_validate(
            model=self.model, user=self.user, operation=self.operation, change_plan=plan
        )

        self.assertIsNone(result.proposal)
        self.assertEqual(len(result.issues), 1)
        issue = result.issues[0]
        self.assertEqual(issue.code, "invalid_field")
        self.assertEqual(issue.target_type, "RelationshipType")
        self.assertEqual(Proposal.objects.count(), proposal_count_before)
        self.assertEqual(ProposalChange.objects.count(), change_count_before)


class CompiledAiProposalOverlayTests(AIServiceTestCase):
    """
    End-to-end regression test for a real production bug: compile_change_plan
    left ObjectType/RelationshipType CREATE changes with parent_type="" and
    parent_id=None (Model isn't part of the Change Plan's EntityRef graph, so
    there is no parent_ref to derive a parent from), but
    model/views/common_context.py's working-overlay builders
    (_build_working_object_types/_build_working_relationship_types) only
    treat a CREATE as proposal-only when parent_type == "Model" -- the exact
    literal every editor-driven CREATE already stamps. The result: an
    Assisted Create proposal's entities existed in the database but never
    appeared in the sidebar or editors, regardless of how/when the active-
    proposal session pointer was set.

    Earlier regression tests covering "the selected AI proposal drives the
    UI" missed this because they built ProposalChange rows by hand with the
    correct parent_type already set, instead of going through the real
    compiler -- which is exactly what Assisted Create does. This test uses
    the actual compile_change_plan output and the real click-to-select view
    request (not a session-poking shortcut), so a regression in either the
    compiler's parent stamping or the view's active-proposal handling would
    fail it.
    """

    def setUp(self):
        self.model = self.make_model()

        WorkspaceMember.objects.create(
            workspace=self.workspace,
            user=self.user,
            role=WorkspaceMember.Role.OWNER,
        )

        self.client.force_login(self.user)

    def test_a_compiled_ai_proposal_is_selectable_and_its_entities_overlay_correctly(self):
        proposal = ProposalService.create_working(
            self.model, self.user, source=Proposal.Source.AI
        )

        plan = ChangePlan(
            actions=[
                ChangeAction(
                    operation="create",
                    target_type="ObjectType",
                    target_ref=_new("tmp:object_type"),
                    fields={"name": "Customer Type", "key": "customer_type"},
                ),
                ChangeAction(
                    operation="create",
                    target_type="RelationshipType",
                    target_ref=_new("tmp:relationship_type"),
                    fields={"name": "Connects To", "key": "connects_to"},
                ),
            ]
        )

        compile_change_plan(
            model=self.model, user=self.user, change_plan=plan, proposal=proposal
        )

        # The real click-to-select flow: a plain GET to the proposal detail
        # URL, exactly what the sidebar's proposal link issues.
        response = self.client.get(
            reverse("model:proposal", args=[self.model.id, proposal.id])
        )
        self.assertEqual(response.status_code, 200)

        self.assertEqual(response.context["active_proposal"].id, proposal.id)

        object_type_keys = {ot.key for ot in response.context["object_types"]}
        self.assertIn("customer_type", object_type_keys)

        relationship_type_keys = {
            rt.key for rt in response.context["relationship_types"]
        }
        self.assertIn("connects_to", relationship_type_keys)

        # Canonical model state is untouched -- compile_change_plan only
        # ever writes ProposalChange rows.
        self.assertEqual(ObjectType.objects.filter(model=self.model).count(), 0)
        self.assertEqual(RelationshipType.objects.filter(model=self.model).count(), 0)
