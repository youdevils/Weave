"""
The compact ontology catalogue: every ObjectType/RelationshipType (active and
inactive), its AttributeDefinitions and its RelationshipTypeRules, identified
only by keys. Replaces ai.services.ontology_context -- there are no
precomposed `ref`/`definitionRef` strings to copy any more, because
AI-facing references are structured (ai.services.change_set).

Discovery receives the whole catalogue (it cannot know in advance which types
are relevant); Planning receives a slice (see ai.services.semantic.selection).
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from ai.services.semantic.index import OBJECT_TYPE, IAttribute, IType, SemanticModelIndex


class CatalogueAttribute(BaseModel):
    key: str
    name: str
    data_type: str
    required: bool = False
    nullable: bool = False
    choices: list[str] = Field(default_factory=list)
    active: bool = True


class Cardinality(BaseModel):
    minimum: int = 0
    maximum: Optional[int] = None


class CatalogueRule(BaseModel):
    subject_type_key: str
    object_type_key: str
    # How many objects (of object_type) each subject must/may have, and how
    # many subjects each object must/may have -- RelationshipTypeRule's own
    # object_minimum/maximum and subject_minimum/maximum.
    objects_per_subject: Cardinality
    subjects_per_object: Cardinality


class CatalogueObjectType(BaseModel):
    key: str
    name: str
    description: str = ""
    active: bool = True
    attributes: list[CatalogueAttribute] = Field(default_factory=list)


class CatalogueRelationshipType(BaseModel):
    key: str
    name: str
    description: str = ""
    active: bool = True
    attributes: list[CatalogueAttribute] = Field(default_factory=list)
    rules: list[CatalogueRule] = Field(default_factory=list)


class OntologyCatalogue(BaseModel):
    object_types: list[CatalogueObjectType] = Field(default_factory=list)
    relationship_types: list[CatalogueRelationshipType] = Field(default_factory=list)

    def is_empty(self) -> bool:
        return not self.object_types and not self.relationship_types


def catalogue_attribute(attribute: IAttribute) -> CatalogueAttribute:
    return CatalogueAttribute(
        key=attribute.key,
        name=attribute.name,
        data_type=attribute.data_type,
        required=attribute.required,
        nullable=attribute.nullable,
        choices=[str(choice) for choice in attribute.choices],
        active=attribute.is_active,
    )


def catalogue_object_type(index: SemanticModelIndex, item: IType) -> CatalogueObjectType:
    return CatalogueObjectType(
        key=item.key,
        name=item.name,
        description=item.description,
        active=item.is_active,
        attributes=[catalogue_attribute(a) for a in index.attributes_of(item.id)],
    )


def catalogue_rule(index: SemanticModelIndex, rule) -> CatalogueRule:
    return CatalogueRule(
        subject_type_key=index.object_types[rule.subject_type_id].key,
        object_type_key=index.object_types[rule.object_type_id].key,
        objects_per_subject=Cardinality(minimum=rule.object_minimum, maximum=rule.object_maximum),
        subjects_per_object=Cardinality(minimum=rule.subject_minimum, maximum=rule.subject_maximum),
    )


def catalogue_relationship_type(
    index: SemanticModelIndex, item: IType, *, object_type_ids=None
) -> CatalogueRelationshipType:
    rules = [
        rule
        for rule in index.rules_of(item.id)
        if object_type_ids is None
        or (rule.subject_type_id in object_type_ids and rule.object_type_id in object_type_ids)
    ]
    return CatalogueRelationshipType(
        key=item.key,
        name=item.name,
        description=item.description,
        active=item.is_active,
        attributes=[catalogue_attribute(a) for a in index.attributes_of(item.id)],
        rules=[catalogue_rule(index, rule) for rule in rules],
    )


def build_catalogue(
    index: SemanticModelIndex,
    *,
    object_type_ids=None,
    relationship_type_ids=None,
) -> OntologyCatalogue:
    """
    The whole catalogue by default; a slice when either id set is given. A
    sliced RelationshipType only lists rules whose two endpoint types are
    both in the slice, so a slice never names a type it doesn't describe.
    """

    object_types = [
        t for t in index.object_types.values() if object_type_ids is None or t.id in object_type_ids
    ]
    relationship_types = [
        t
        for t in index.relationship_types.values()
        if relationship_type_ids is None or t.id in relationship_type_ids
    ]
    included_object_type_ids = {t.id for t in object_types}

    return OntologyCatalogue(
        object_types=[catalogue_object_type(index, t) for t in object_types],
        relationship_types=[
            catalogue_relationship_type(
                index,
                t,
                object_type_ids=None if object_type_ids is None else included_object_type_ids,
            )
            for t in relationship_types
        ],
    )


def type_kind_label(kind: str) -> str:
    return "ObjectType" if kind == OBJECT_TYPE else "RelationshipType"
