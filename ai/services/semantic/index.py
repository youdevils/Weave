"""
SemanticModelIndex: a read-only, canonical-only snapshot of one Model, loaded
straight from the ORM, keyed both by canonical UUID (OnyxJar-internal) and by
semantic identity (keys / key triples -- what AI-facing references use).

Deliberately not model.services.model_graph.EffectiveDataset: that dataset is
a viewer/proposal-overlay read model that drops inactive Objects and
Relationships entirely (and inactive types by default), which made an
inactive entity unresolvable -- so an AI could never reactivate one and
instead proposed a suffixed duplicate. This index keeps every row and
carries `is_active`, so lifecycle state is visible and resolvable.

Never reads proposal state: AI context is always canonical (see
ai.services.staging for how a candidate ChangeSet is evaluated speculatively
instead).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from django.db.models import Q

from model.models.attribute_definition import AttributeDefinition
from model.models.object import Object
from model.models.object_type import ObjectType
from model.models.relationship import Relationship
from model.models.relationship_type import RelationshipType
from model.models.relationship_type_rule import RelationshipTypeRule
from model.services.keys import slugify_key

OBJECT_TYPE = "object_type"
RELATIONSHIP_TYPE = "relationship_type"


def normalize_name(value) -> str:
    """Case/accent/punctuation-insensitive form of a human name, for matching only."""

    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^0-9a-z]+", " ", text.casefold())
    return " ".join(text.split())


def _iso(value):
    return value.isoformat() if value is not None else None


@dataclass(frozen=True)
class IType:
    id: str
    kind: str  # OBJECT_TYPE | RELATIONSHIP_TYPE
    key: str
    name: str
    description: str
    is_active: bool


@dataclass(frozen=True)
class IAttribute:
    id: str
    owner_kind: str  # OBJECT_TYPE | RELATIONSHIP_TYPE
    owner_id: str
    key: str
    name: str
    data_type: str
    description: str
    required: bool
    nullable: bool
    config: dict
    is_active: bool

    @property
    def choices(self) -> list:
        return list((self.config or {}).get("choices") or [])


@dataclass(frozen=True)
class IRule:
    id: str
    relationship_type_id: str
    subject_type_id: str
    object_type_id: str
    subject_minimum: int
    subject_maximum: int | None
    object_minimum: int
    object_maximum: int | None


@dataclass(frozen=True)
class IObject:
    id: str
    type_id: str
    key: str
    name: str
    description: str
    attributes: dict
    is_active: bool


@dataclass(frozen=True)
class IRelationship:
    id: str
    type_id: str
    subject_id: str
    object_id: str
    attributes: dict
    valid_from: str | None
    valid_to: str | None
    is_active: bool


@dataclass(frozen=True)
class ObjectMatch:
    object: IObject
    match: str  # "key" | "name" | "alias"


@dataclass
class SemanticModelIndex:
    object_types: dict[str, IType] = field(default_factory=dict)
    relationship_types: dict[str, IType] = field(default_factory=dict)
    attributes: dict[str, IAttribute] = field(default_factory=dict)
    rules: dict[str, IRule] = field(default_factory=dict)
    objects: dict[str, IObject] = field(default_factory=dict)
    relationships: dict[str, IRelationship] = field(default_factory=dict)

    def __post_init__(self):
        self._reindex()

    # -- loading ---------------------------------------------------------

    @classmethod
    def load(cls, model) -> "SemanticModelIndex":
        object_types = {
            str(row["id"]): IType(
                id=str(row["id"]), kind=OBJECT_TYPE, key=row["key"], name=row["name"],
                description=row["description"] or "", is_active=row["is_active"],
            )
            for row in ObjectType.objects.filter(model=model)
            .order_by("sort_order", "name", "id")
            .values("id", "key", "name", "description", "is_active")
        }
        relationship_types = {
            str(row["id"]): IType(
                id=str(row["id"]), kind=RELATIONSHIP_TYPE, key=row["key"], name=row["name"],
                description=row["description"] or "", is_active=row["is_active"],
            )
            for row in RelationshipType.objects.filter(model=model)
            .order_by("sort_order", "name", "id")
            .values("id", "key", "name", "description", "is_active")
        }

        attributes = {}
        for row in (
            AttributeDefinition.objects.filter(Q(object_type__model=model) | Q(relationship_type__model=model))
            .order_by("sort_order", "name", "id")
            .values(
                "id", "object_type_id", "relationship_type_id", "key", "name", "data_type",
                "description", "required", "nullable", "config", "is_active",
            )
        ):
            if row["object_type_id"] is not None:
                owner_kind, owner_id = OBJECT_TYPE, str(row["object_type_id"])
            else:
                owner_kind, owner_id = RELATIONSHIP_TYPE, str(row["relationship_type_id"])
            attributes[str(row["id"])] = IAttribute(
                id=str(row["id"]), owner_kind=owner_kind, owner_id=owner_id, key=row["key"],
                name=row["name"], data_type=row["data_type"], description=row["description"] or "",
                required=row["required"], nullable=row["nullable"], config=dict(row["config"] or {}),
                is_active=row["is_active"],
            )

        rules = {
            str(row["id"]): IRule(
                id=str(row["id"]),
                relationship_type_id=str(row["relationship_type_id"]),
                subject_type_id=str(row["subject_type_id"]),
                object_type_id=str(row["object_type_id"]),
                subject_minimum=row["subject_minimum"],
                subject_maximum=row["subject_maximum"],
                object_minimum=row["object_minimum"],
                object_maximum=row["object_maximum"],
            )
            for row in RelationshipTypeRule.objects.filter(relationship_type__model=model)
            .order_by("id")
            .values(
                "id", "relationship_type_id", "subject_type_id", "object_type_id",
                "subject_minimum", "subject_maximum", "object_minimum", "object_maximum",
            )
        }

        objects = {
            str(row["id"]): IObject(
                id=str(row["id"]), type_id=str(row["object_type_id"]), key=row["key"] or "",
                name=row["name"], description=row["description"] or "",
                attributes=dict(row["attributes"] or {}), is_active=row["is_active"],
            )
            for row in Object.objects.filter(model=model)
            .order_by("name", "id")
            .values("id", "object_type_id", "key", "name", "description", "attributes", "is_active")
        }

        relationships = {
            str(row["id"]): IRelationship(
                id=str(row["id"]), type_id=str(row["relationship_type_id"]),
                subject_id=str(row["subject_id"]), object_id=str(row["object_id"]),
                attributes=dict(row["attributes"] or {}), valid_from=_iso(row["valid_from"]),
                valid_to=_iso(row["valid_to"]), is_active=row["is_active"],
            )
            for row in Relationship.objects.filter(model=model)
            .order_by("id")
            .values(
                "id", "relationship_type_id", "subject_id", "object_id", "attributes",
                "valid_from", "valid_to", "is_active",
            )
        }

        return cls(
            object_types=object_types,
            relationship_types=relationship_types,
            attributes=attributes,
            rules=rules,
            objects=objects,
            relationships=relationships,
        )

    def _reindex(self) -> None:
        self._object_types_by_key = {t.key: t for t in self.object_types.values()}
        self._relationship_types_by_key = {t.key: t for t in self.relationship_types.values()}
        self._attributes_by_owner: dict[str, list[IAttribute]] = {}
        for attribute in self.attributes.values():
            self._attributes_by_owner.setdefault(attribute.owner_id, []).append(attribute)
        self._rules_by_triple = {
            (r.relationship_type_id, r.subject_type_id, r.object_type_id): r for r in self.rules.values()
        }
        self._objects_by_type: dict[str, list[IObject]] = {}
        self._objects_by_type_key: dict[tuple[str, str], IObject] = {}
        for obj in self.objects.values():
            self._objects_by_type.setdefault(obj.type_id, []).append(obj)
            if obj.key:
                self._objects_by_type_key[(obj.type_id, obj.key)] = obj
        self._relationships_by_object: dict[str, list[IRelationship]] = {}
        self._relationships_by_triple: dict[tuple[str, str, str], list[IRelationship]] = {}
        for relationship in self.relationships.values():
            self._relationships_by_object.setdefault(relationship.subject_id, []).append(relationship)
            if relationship.object_id != relationship.subject_id:
                self._relationships_by_object.setdefault(relationship.object_id, []).append(relationship)
            self._relationships_by_triple.setdefault(
                (relationship.type_id, relationship.subject_id, relationship.object_id), []
            ).append(relationship)

    # -- type lookups ----------------------------------------------------

    def type_by_key(self, kind: str, key) -> IType | None:
        if kind == OBJECT_TYPE:
            return self._object_types_by_key.get(key)
        if kind == RELATIONSHIP_TYPE:
            return self._relationship_types_by_key.get(key)
        return None

    def object_type_by_key(self, key) -> IType | None:
        return self._object_types_by_key.get(key)

    def relationship_type_by_key(self, key) -> IType | None:
        return self._relationship_types_by_key.get(key)

    def type_by_id(self, type_id) -> IType | None:
        type_id = str(type_id)
        return self.object_types.get(type_id) or self.relationship_types.get(type_id)

    def types_named(self, kind: str, name) -> list[IType]:
        wanted = normalize_name(name)
        pool = self.object_types if kind == OBJECT_TYPE else self.relationship_types
        slug = slugify_key(name)
        return [t for t in pool.values() if normalize_name(t.name) == wanted or (slug and t.key == slug)]

    # -- attribute lookups -----------------------------------------------

    def attributes_of(self, owner_id) -> list[IAttribute]:
        return list(self._attributes_by_owner.get(str(owner_id), []))

    def attribute(self, owner_id, key) -> IAttribute | None:
        for attribute in self._attributes_by_owner.get(str(owner_id), []):
            if attribute.key == key:
                return attribute
        return None

    # -- rule lookups ----------------------------------------------------

    def rule(self, relationship_type_id, subject_type_id, object_type_id) -> IRule | None:
        return self._rules_by_triple.get((str(relationship_type_id), str(subject_type_id), str(object_type_id)))

    def rules_of(self, relationship_type_id) -> list[IRule]:
        rid = str(relationship_type_id)
        return [r for r in self.rules.values() if r.relationship_type_id == rid]

    def rules_touching(self, object_type_id) -> list[IRule]:
        tid = str(object_type_id)
        return [r for r in self.rules.values() if tid in (r.subject_type_id, r.object_type_id)]

    # -- object / relationship lookups -------------------------------------

    def object_by_key(self, type_id, key) -> IObject | None:
        return self._objects_by_type_key.get((str(type_id), key))

    def objects_of_type(self, type_id) -> list[IObject]:
        return list(self._objects_by_type.get(str(type_id), []))

    def relationships_of(self, object_id) -> list[IRelationship]:
        return list(self._relationships_by_object.get(str(object_id), []))

    def relationships_matching(self, type_id, subject_id, object_id) -> list[IRelationship]:
        return list(self._relationships_by_triple.get((str(type_id), str(subject_id), str(object_id)), []))

    def match_objects(self, type_id, name, aliases=()) -> list[ObjectMatch]:
        """
        Deterministic identity hints for a described entity: an existing
        Object of the type whose key equals the name's slug, or whose name
        equals the name/an alias case-, accent- and punctuation-insensitively.
        Hints only -- OnyxJar never auto-binds a candidate to a match.
        """

        wanted = {normalize_name(name): "name"}
        for alias in aliases or ():
            wanted.setdefault(normalize_name(alias), "alias")
        wanted.pop("", None)
        slugs = {slugify_key(value) for value in (name, *(aliases or ())) if value}
        slugs.discard("")

        matches = []
        for obj in self._objects_by_type.get(str(type_id), []):
            if obj.key and obj.key in slugs:
                matches.append(ObjectMatch(obj, "key"))
                continue
            kind = wanted.get(normalize_name(obj.name))
            if kind:
                matches.append(ObjectMatch(obj, kind))
        return matches

    # -- semantic identity (OnyxJar-internal UUID -> AI-facing reference) ----

    def semantic_ref(self, target_type: str, target_id) -> dict | None:
        """The AI-facing semantic reference for a canonical entity, or None."""

        target_id = str(target_id)

        if target_type in ("ObjectType", "RelationshipType"):
            item = self.type_by_id(target_id)
            return {"entity": item.kind, "key": item.key} if item else None

        if target_type == "AttributeDefinition":
            item = self.attributes.get(target_id)
            owner = self.type_by_id(item.owner_id) if item else None
            if not owner:
                return None
            return {"entity": "attribute", "owner_kind": item.owner_kind, "owner_key": owner.key, "key": item.key}

        if target_type == "RelationshipTypeRule":
            item = self.rules.get(target_id)
            if not item:
                return None
            return {
                "entity": "rule",
                "relationship_type_key": self.relationship_types[item.relationship_type_id].key,
                "subject_type_key": self.object_types[item.subject_type_id].key,
                "object_type_key": self.object_types[item.object_type_id].key,
            }

        if target_type == "Object":
            item = self.objects.get(target_id)
            return self.object_identity(item) if item else None

        if target_type == "Relationship":
            item = self.relationships.get(target_id)
            if not item:
                return None
            return {
                "entity": "relationship",
                "relationship_type_key": self.relationship_types[item.type_id].key,
                "subject": self.object_identity(self.objects[item.subject_id]),
                "object": self.object_identity(self.objects[item.object_id]),
            }

        return None

    def object_identity(self, obj: IObject) -> dict:
        return {
            "entity": "object",
            "type_key": self.object_types[obj.type_id].key,
            "key": obj.key,
            "name": obj.name,
        }
