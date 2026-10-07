"""
Semantic records: how one canonical Object or Relationship is described to an
AI stage. Raw stored values only, identified by keys -- no canonical UUIDs,
and none of the Explorer details payload's viewer fields (display strings,
inView/hiddenConnectionIds, connectionCount, isProposed/isCreated).
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

from ai.services.semantic.index import IObject, IRelationship, SemanticModelIndex


class ObjectIdentity(BaseModel):
    type_key: str
    key: str
    name: str


class ObjectRecord(BaseModel):
    type_key: str
    key: str
    name: str
    description: str = ""
    active: bool = True
    attributes: dict[str, Any] = Field(default_factory=dict)


class RelationshipRecord(BaseModel):
    relationship_type_key: str
    subject: ObjectIdentity
    object: ObjectIdentity
    active: bool = True
    attributes: dict[str, Any] = Field(default_factory=dict)
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None


def object_identity(index: SemanticModelIndex, obj: IObject) -> ObjectIdentity:
    return ObjectIdentity(type_key=index.object_types[obj.type_id].key, key=obj.key, name=obj.name)


def object_record(index: SemanticModelIndex, obj: IObject) -> ObjectRecord:
    return ObjectRecord(
        type_key=index.object_types[obj.type_id].key,
        key=obj.key,
        name=obj.name,
        description=obj.description,
        active=obj.is_active,
        attributes=dict(obj.attributes),
    )


def relationship_record(index: SemanticModelIndex, relationship: IRelationship) -> RelationshipRecord:
    return RelationshipRecord(
        relationship_type_key=index.relationship_types[relationship.type_id].key,
        subject=object_identity(index, index.objects[relationship.subject_id]),
        object=object_identity(index, index.objects[relationship.object_id]),
        active=relationship.is_active,
        attributes=dict(relationship.attributes),
        valid_from=relationship.valid_from,
        valid_to=relationship.valid_to,
    )
