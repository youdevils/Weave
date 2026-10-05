from django.test import SimpleTestCase

from model.services.model_graph.dataset import EffectiveDataset

from .builders import (
    ALICE,
    ALICE_TWO,
    APP,
    BOB,
    LONER,
    MEMBER_OF,
    OPS,
    PERSON,
    TEAM,
    USES,
    WEB,
    attribute_definition,
    object_type,
    obj,
    rel,
    relationship_type,
    relationship_type_rule,
    rule,
    sample_dataset,
    uid,
)


class DatasetInvariantTests(SimpleTestCase):

    def test_relationship_with_a_missing_endpoint_is_dropped(self):
        dataset = EffectiveDataset(
            object_types=[object_type(PERSON, "Person")],
            relationship_types=[relationship_type(MEMBER_OF, "Member of")],
            objects=[obj(ALICE, PERSON, "Alice")],
            relationships=[rel(1, MEMBER_OF, ALICE, 999)],
        )

        self.assertEqual(dataset.relationships, {})

    def test_objects_of_unknown_types_and_relationships_of_unknown_types_are_dropped(self):
        dataset = EffectiveDataset(
            object_types=[object_type(PERSON, "Person")],
            relationship_types=[relationship_type(MEMBER_OF, "Member of")],
            objects=[obj(ALICE, PERSON, "Alice"), obj(BOB, TEAM, "Ghost type")],
            relationships=[rel(1, USES, ALICE, ALICE)],
        )

        self.assertEqual(list(dataset.objects), [uid(ALICE)])
        self.assertEqual(dataset.relationships, {})

    def test_objects_are_ordered_by_name_then_id(self):
        dataset = sample_dataset()
        names = [o.name for o in dataset.objects.values()]

        self.assertEqual(names, sorted(names, key=str.lower))
        # The two "Alice"s sit together in id order.
        self.assertEqual(
            [o.id for o in dataset.objects.values() if o.name == "Alice"], [uid(ALICE), uid(ALICE_TWO)]
        )

    def test_lookups_accept_uuid_or_string(self):
        dataset = sample_dataset()

        self.assertEqual(dataset.object(uid(OPS)).name, "Ops")
        self.assertIsNone(dataset.object("not-an-id"))
        self.assertIsNone(dataset.relationship(uid(999999)))


class AdjacencyTests(SimpleTestCase):

    def test_relationships_of_covers_both_directions(self):
        dataset = sample_dataset()

        ops = dataset.relationships_of(OPS_ID := uid(OPS))
        self.assertEqual(len(ops), 4)  # two incoming member_of, two outgoing uses
        self.assertEqual(dataset.degree(OPS_ID), 4)
        self.assertEqual(dataset.degree(uid(LONER)), 0)

    def test_self_relationship_counts_once(self):
        dataset = EffectiveDataset(
            object_types=[object_type(APP, "Application")],
            relationship_types=[relationship_type(USES, "Uses")],
            objects=[obj(WEB, APP, "Web")],
            relationships=[rel(1, USES, WEB, WEB)],
        )

        self.assertEqual(dataset.degree(uid(WEB)), 1)

    def test_rule_for_finds_the_matching_cardinality_rule(self):
        dataset = sample_dataset()
        relationship = dataset.relationship(uid(1003))  # Ops uses Web

        found = dataset.rule_for(relationship)

        self.assertEqual((found.subject_minimum, found.object_maximum), (1, 1))

    def test_rule_for_is_none_without_a_matching_rule(self):
        dataset = EffectiveDataset(
            object_types=[object_type(PERSON, "Person"), object_type(TEAM, "Team")],
            relationship_types=[relationship_type(MEMBER_OF, "Member of", [rule(TEAM, PERSON)])],
            objects=[obj(ALICE, PERSON, "Alice"), obj(OPS, TEAM, "Ops")],
            relationships=[rel(1, MEMBER_OF, ALICE, OPS)],
        )

        self.assertIsNone(dataset.rule_for(dataset.relationship(uid(1))))


class KeyLookupTests(SimpleTestCase):
    """
    The AI-facing key-based lookups (ai.services.change_plan's domain
    table): every "existing"-kind EntityRef resolves against one of these,
    except the "relationship" domain, which has no key-based counterpart at
    all (see dataset.relationship, unaffected here) -- Relationship has no
    key and no uniqueness constraint that could ever back a safe synthetic
    composite.
    """

    def test_object_type_by_key(self):
        dataset = sample_dataset()

        self.assertEqual(dataset.object_type_by_key("person").id, uid(PERSON))
        self.assertIsNone(dataset.object_type_by_key("does_not_exist"))

    def test_relationship_type_by_key(self):
        dataset = sample_dataset()

        self.assertEqual(dataset.relationship_type_by_key("uses").id, uid(USES))
        self.assertIsNone(dataset.relationship_type_by_key("does_not_exist"))

    def test_object_by_key(self):
        dataset = sample_dataset()

        self.assertEqual(dataset.object_by_key("person:alice").id, uid(ALICE))
        self.assertEqual(dataset.object_by_key("person:alice_two").id, uid(ALICE_TWO))

    def test_object_by_key_malformed_or_unknown_is_none(self):
        dataset = sample_dataset()

        self.assertIsNone(dataset.object_by_key("alice"))  # missing "type:" prefix -- wrong arity
        self.assertIsNone(dataset.object_by_key("ghost_type:alice"))  # unknown type
        self.assertIsNone(dataset.object_by_key("person:ghost"))  # unknown object key

    def test_relationship_type_rule_by_key(self):
        dataset = EffectiveDataset(
            object_types=[object_type(PERSON, "Person"), object_type(TEAM, "Team")],
            relationship_types=[relationship_type(MEMBER_OF, "Member of")],
            objects=[],
            relationships=[],
            relationship_type_rules=[relationship_type_rule(1, MEMBER_OF, PERSON, TEAM)],
        )

        found = dataset.relationship_type_rule_by_key("member_of:person:team")
        self.assertIsNotNone(found)
        self.assertEqual(found.relationship_type_id, uid(MEMBER_OF))

    def test_relationship_type_rule_by_key_malformed_or_unknown_is_none(self):
        dataset = EffectiveDataset(
            object_types=[object_type(PERSON, "Person"), object_type(TEAM, "Team")],
            relationship_types=[relationship_type(MEMBER_OF, "Member of")],
            objects=[],
            relationships=[],
            relationship_type_rules=[relationship_type_rule(1, MEMBER_OF, PERSON, TEAM)],
        )

        self.assertIsNone(dataset.relationship_type_rule_by_key("member_of:person"))  # wrong arity
        self.assertIsNone(dataset.relationship_type_rule_by_key("ghost:person:team"))  # unknown type
        self.assertIsNone(dataset.relationship_type_rule_by_key("member_of:team:person"))  # swapped pair

    def test_attribute_definition_by_key(self):
        dataset = EffectiveDataset(
            object_types=[object_type(PERSON, "Person")],
            relationship_types=[],
            objects=[],
            relationships=[],
            attribute_definitions=[
                attribute_definition(1, "email", "Email", "text", parent_type="ObjectType", parent_number=PERSON)
            ],
        )

        found = dataset.attribute_definition_by_key("ObjectType:person:email")
        self.assertIsNotNone(found)
        self.assertEqual(found.key, "email")

    def test_attribute_definition_by_key_malformed_or_unknown_is_none(self):
        dataset = EffectiveDataset(
            object_types=[object_type(PERSON, "Person")],
            relationship_types=[],
            objects=[],
            relationships=[],
            attribute_definitions=[
                attribute_definition(1, "email", "Email", "text", parent_type="ObjectType", parent_number=PERSON)
            ],
        )

        self.assertIsNone(dataset.attribute_definition_by_key("person:email"))  # wrong arity
        self.assertIsNone(dataset.attribute_definition_by_key("Object:person:email"))  # bad literal
        self.assertIsNone(dataset.attribute_definition_by_key("RelationshipType:person:email"))  # wrong parent type
