from django.test import SimpleTestCase

from model.services.model_graph.dataset import EffectiveDataset
from model.services.model_graph.tests.builders import (
    object_type,
    relationship_type,
    relationship_type_rule,
    spec,
)

from ai.services.ontology_context import compile_ontology_context

PERSON, TEAM, APP = 1, 2, 3
MEMBER_OF = 11


class CompileOntologyContextTests(SimpleTestCase):

    def test_a_relationship_type_with_two_rules_produces_one_entry_not_two(self):
        """
        The structural fix for Bug A: model.services.ontology_graph.compiler
        emits one graph *edge* per RelationshipTypeRule (needed for
        rendering -- a RelationshipType can fan out into several rules,
        each its own subject/object ObjectType pair), with the edge's
        top-level id being the Rule's id, not the RelationshipType's --
        exactly the id an AI mistakenly picked in production. This builder
        groups by RelationshipType instead, and must never expose a bare
        rule/edge id anywhere in its output.
        """

        dataset = EffectiveDataset(
            object_types=[
                object_type(PERSON, "Person"),
                object_type(TEAM, "Team"),
                object_type(APP, "Application"),
            ],
            relationship_types=[relationship_type(MEMBER_OF, "Member of")],
            objects=[],
            relationships=[],
            relationship_type_rules=[
                relationship_type_rule(101, MEMBER_OF, PERSON, TEAM),
                relationship_type_rule(102, MEMBER_OF, PERSON, APP),
            ],
        )

        context = compile_ontology_context(dataset)

        self.assertEqual(len(context["relationship_types"]), 1)
        entry = context["relationship_types"][0]
        self.assertEqual(entry["key"], "member_of")

        self.assertEqual(len(entry["rules"]), 2)
        refs = {rule["ref"] for rule in entry["rules"]}
        self.assertEqual(refs, {"member_of:person:team", "member_of:person:application"})

        # No bare rule/edge id anywhere -- every identifier is either the
        # RelationshipType's own key (checked above) or a rule's precomposed
        # `ref` composite (also checked above). Nothing else is exposed.
        for rule in entry["rules"]:
            self.assertEqual(set(rule.keys()), {"ref", "subjectTypeKey", "objectTypeKey", "cardinality"})

    def test_object_type_attributes_expose_a_precomposed_definition_ref(self):
        dataset = EffectiveDataset(
            object_types=[object_type(PERSON, "Person", [spec("email", "text", name="Email")])],
            relationship_types=[],
            objects=[],
            relationships=[],
        )

        context = compile_ontology_context(dataset)

        entry = context["object_types"][0]
        self.assertEqual(entry["key"], "person")
        self.assertEqual(
            entry["attributes"],
            [{"key": "email", "name": "Email", "dataType": "text", "definitionRef": "ObjectType:person:email"}],
        )

    def test_empty_dataset_produces_empty_lists(self):
        dataset = EffectiveDataset(object_types=[], relationship_types=[], objects=[], relationships=[])

        context = compile_ontology_context(dataset)

        self.assertEqual(context, {"object_types": [], "relationship_types": []})
