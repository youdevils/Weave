"""
The AI-facing ontology payload: a purpose-built representation, not a reuse
of model.services.ontology_graph.compiler.compile_ontology_graph (which
exists to drive the Explorer UI's vis-network rendering and is keyed at
RelationshipTypeRule granularity -- one edge per rule, since a single
RelationshipType can fan out into several rules, each its own distinct
subject/object ObjectType pair, and vis-network requires one globally
unique id per edge with exactly one source/target pair).

That rendering-shaped id (a RelationshipTypeRule's own id, not the
RelationshipType's) previously leaked into AI context verbatim, and an AI
asked to reference a RelationshipType by "the id in context" could pick the
wrong entity's id. This module groups by RelationshipType instead -- never
by Rule -- and never exposes a bare rule/edge id at all: every identifier
here is either a real `key` (unique per Model, for ObjectType/
RelationshipType) or a precomposed, copy-verbatim `ref`/`definitionRef`
composite string (see ai.services.change_plan's domain table for the exact
format per domain). The AI never assembles these strings itself.

Zero changes to compile_ontology_graph/ViewerPayload or any Explorer/
Customise/Overview rendering code -- this is a parallel, AI-specific
builder reading directly from the same EffectiveDataset ai.services.
context_builder already loads, not a modification of shared code.
"""

from __future__ import annotations


def _attribute_entries(dataset, attributes, *, parent_type: str, parent_key: str) -> list[dict]:
    return [
        {
            "key": spec.key,
            "name": spec.name,
            "dataType": spec.data_type,
            "definitionRef": f"{parent_type}:{parent_key}:{spec.key}",
        }
        for spec in attributes
    ]


def _rule_entries(dataset, relationship_type) -> list[dict]:
    entries = []
    for rule in dataset.relationship_type_rules.values():
        if rule.relationship_type_id != relationship_type.id:
            continue
        subject_type = dataset.object_types.get(rule.subject_type_id)
        object_type = dataset.object_types.get(rule.object_type_id)
        if subject_type is None or object_type is None:
            continue
        entries.append(
            {
                "ref": f"{relationship_type.key}:{subject_type.key}:{object_type.key}",
                "subjectTypeKey": subject_type.key,
                "objectTypeKey": object_type.key,
                "cardinality": {
                    "subject": {"minimum": rule.subject_minimum, "maximum": rule.subject_maximum},
                    "object": {"minimum": rule.object_minimum, "maximum": rule.object_maximum},
                },
            }
        )
    return entries


def compile_ontology_context(dataset) -> dict:
    return {
        "object_types": [
            {
                "key": object_type.key,
                "name": object_type.name,
                "attributes": _attribute_entries(
                    dataset, object_type.attributes, parent_type="ObjectType", parent_key=object_type.key
                ),
            }
            for object_type in dataset.object_types.values()
        ],
        "relationship_types": [
            {
                "key": relationship_type.key,
                "name": relationship_type.name,
                "attributes": _attribute_entries(
                    dataset,
                    relationship_type.attributes,
                    parent_type="RelationshipType",
                    parent_key=relationship_type.key,
                ),
                "rules": _rule_entries(dataset, relationship_type),
            }
            for relationship_type in dataset.relationship_types.values()
        ],
    }
