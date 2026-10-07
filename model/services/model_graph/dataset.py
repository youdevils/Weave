"""
The effective model dataset: what Objects and Relationships actually exist
once the canonical model and the current user's active proposal are combined.

These are plain, immutable-ish value objects with no ORM, DOM or viewer
knowledge, so projection, search and details logic can be tested with
hand-built datasets and a future list/table view can consume the same data.

Invariants enforced by ``EffectiveDataset`` itself (so a hand-built dataset
cannot violate them):
  * an object's type is a known object type;
  * a relationship's type is a known relationship type;
  * both endpoints of a relationship are objects in the dataset.
Inactive Objects and Relationships never enter the dataset. Inactive *types*
are known only when the loader was asked to keep those that still hold active
records (``keep_inactive_types``); by default only active types are known.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class AttributeSpec:
    key: str
    name: str
    data_type: str  # text | number | boolean | date | datetime | choice | url
    choices: tuple[str, ...] = ()


@dataclass(frozen=True)
class CardinalityRule:
    subject_type_id: str
    object_type_id: str
    subject_minimum: int
    subject_maximum: int | None
    object_minimum: int
    object_maximum: int | None


@dataclass(frozen=True)
class EffectiveObjectType:
    id: str
    key: str
    name: str
    is_proposed: bool = False
    attributes: tuple[AttributeSpec, ...] = ()


@dataclass(frozen=True)
class EffectiveRelationshipType:
    id: str
    key: str
    name: str
    is_proposed: bool = False
    attributes: tuple[AttributeSpec, ...] = ()
    rules: tuple[CardinalityRule, ...] = ()


@dataclass(frozen=True)
class EffectiveObject:
    id: str
    type_id: str
    name: str
    key: str = ""
    description: str = ""
    attributes: dict = field(default_factory=dict)
    is_proposed: bool = False
    is_created: bool = False


@dataclass(frozen=True)
class EffectiveRelationship:
    id: str
    type_id: str
    source_id: str
    target_id: str
    attributes: dict = field(default_factory=dict)
    valid_from: str | None = None
    valid_to: str | None = None
    is_proposed: bool = False
    is_created: bool = False


@dataclass(frozen=True)
class EffectiveAttributeDefinition:
    """
    Key-path addressability for an AttributeDefinition
    ("{ObjectType|RelationshipType}:{parent_key}:{key}" --
    AttributeDefinition.key is only unique within its one parent). Not
    needed by projection/details/reachability; originally added for the
    legacy AI context, which now uses ai.services.semantic.index instead.
    """

    id: str
    key: str
    name: str
    data_type: str
    parent_type: str  # "ObjectType" | "RelationshipType"
    parent_id: str


@dataclass(frozen=True)
class EffectiveRelationshipTypeRule:
    """
    AI-facing addressability for a RelationshipTypeRule -- same rationale
    as EffectiveAttributeDefinition above. Deliberately separate from (and
    duplicates some data already in) CardinalityRule, which stays exactly
    as-is for its own existing nested-display purpose inside
    EffectiveRelationshipType.rules/dataset.rule_for(); this is a parallel,
    top-level, addressable representation, not a replacement.
    """

    id: str
    relationship_type_id: str
    subject_type_id: str
    object_type_id: str
    subject_minimum: int
    subject_maximum: int | None
    object_minimum: int
    object_maximum: int | None


def is_populated(value) -> bool:
    """A stored attribute value counts as populated unless it is None or blank."""
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() != ""
    return True


class EffectiveDataset:

    def __init__(
        self,
        object_types,
        relationship_types,
        objects,
        relationships,
        attribute_definitions=(),
        relationship_type_rules=(),
    ):
        self.object_types = {t.id: t for t in object_types}
        self.relationship_types = {t.id: t for t in relationship_types}

        self.objects = {
            o.id: o
            for o in sorted(objects, key=lambda o: (o.name.lower(), o.id))
            if o.type_id in self.object_types
        }

        self.relationships = {
            r.id: r
            for r in sorted(relationships, key=lambda r: r.id)
            if r.type_id in self.relationship_types
            and r.source_id in self.objects
            and r.target_id in self.objects
        }

        self.attribute_definitions = {
            a.id: a
            for a in attribute_definitions
            if (a.parent_type == "ObjectType" and a.parent_id in self.object_types)
            or (a.parent_type == "RelationshipType" and a.parent_id in self.relationship_types)
        }

        self.relationship_type_rules = {
            r.id: r
            for r in relationship_type_rules
            if r.relationship_type_id in self.relationship_types
            and r.subject_type_id in self.object_types
            and r.object_type_id in self.object_types
        }

        self._adjacency: dict[str, list[EffectiveRelationship]] = {oid: [] for oid in self.objects}
        for relationship in self.relationships.values():
            self._adjacency[relationship.source_id].append(relationship)
            if relationship.target_id != relationship.source_id:
                self._adjacency[relationship.target_id].append(relationship)

        # Key reverse-indices -- AI-facing addressability, built once here
        # from data already loaded above, mirroring the id dicts.
        self._object_types_by_key = {t.key: t for t in self.object_types.values()}
        self._relationship_types_by_key = {t.key: t for t in self.relationship_types.values()}
        self._objects_by_key_path = {
            (o.type_id, o.key): o for o in self.objects.values() if o.key
        }
        self._attribute_definitions_by_key_path = {
            (a.parent_type, a.parent_id, a.key): a for a in self.attribute_definitions.values()
        }
        self._relationship_type_rules_by_key_path = {
            (r.relationship_type_id, r.subject_type_id, r.object_type_id): r
            for r in self.relationship_type_rules.values()
        }

    # -- lookups ---------------------------------------------------------

    def object(self, object_id) -> EffectiveObject | None:
        return self.objects.get(str(object_id))

    def relationship(self, relationship_id) -> EffectiveRelationship | None:
        return self.relationships.get(str(relationship_id))

    def object_type(self, type_id) -> EffectiveObjectType | None:
        return self.object_types.get(str(type_id))

    def relationship_type(self, type_id) -> EffectiveRelationshipType | None:
        return self.relationship_types.get(str(type_id))

    def relationships_of(self, object_id) -> list[EffectiveRelationship]:
        """Every relationship touching the object, in a stable order."""
        return list(self._adjacency.get(str(object_id), []))

    def degree(self, object_id) -> int:
        return len(self._adjacency.get(str(object_id), []))

    def rule_for(self, relationship: EffectiveRelationship) -> CardinalityRule | None:
        relationship_type = self.relationship_types[relationship.type_id]
        source = self.objects[relationship.source_id]
        target = self.objects[relationship.target_id]
        for rule in relationship_type.rules:
            if rule.subject_type_id == source.type_id and rule.object_type_id == target.type_id:
                return rule
        return None

    # -- key-based lookups (AI-facing addressability) ---------------------
    #
    # Originally the resolution target of the legacy AI EntityRef contract
    # (the ai app now resolves semantic references against
    # ai.services.semantic.index instead). There is no key-based Relationship
    # lookup here: Relationship has no key field and no
    # uniqueness constraint on (type, subject, object), so no synthetic
    # composite key could ever be guaranteed safe. dataset.relationship(id)
    # (above) remains the only way to address an existing Relationship.
    #
    # Every lookup here returns None on malformed or unknown input, never
    # raises -- matching the existing .get(...)-based lookup style.

    def object_type_by_key(self, key: str) -> EffectiveObjectType | None:
        return self._object_types_by_key.get(key)

    def relationship_type_by_key(self, key: str) -> EffectiveRelationshipType | None:
        return self._relationship_types_by_key.get(key)

    def object_by_key(self, key_path: str) -> EffectiveObject | None:
        parts = key_path.split(":", 1)
        if len(parts) != 2:
            return None
        type_key, object_key = parts
        object_type = self._object_types_by_key.get(type_key)
        if object_type is None:
            return None
        return self._objects_by_key_path.get((object_type.id, object_key))

    def attribute_definition_by_key(self, key_path: str) -> EffectiveAttributeDefinition | None:
        parts = key_path.split(":", 2)
        if len(parts) != 3:
            return None
        parent_type, parent_key, attribute_key = parts
        if parent_type == "ObjectType":
            parent = self._object_types_by_key.get(parent_key)
        elif parent_type == "RelationshipType":
            parent = self._relationship_types_by_key.get(parent_key)
        else:
            return None
        if parent is None:
            return None
        return self._attribute_definitions_by_key_path.get((parent_type, parent.id, attribute_key))

    def relationship_type_rule_by_key(self, key_path: str) -> EffectiveRelationshipTypeRule | None:
        parts = key_path.split(":", 2)
        if len(parts) != 3:
            return None
        relationship_type_key, subject_type_key, object_type_key = parts
        relationship_type = self._relationship_types_by_key.get(relationship_type_key)
        subject_type = self._object_types_by_key.get(subject_type_key)
        object_type = self._object_types_by_key.get(object_type_key)
        if relationship_type is None or subject_type is None or object_type is None:
            return None
        return self._relationship_type_rules_by_key_path.get(
            (relationship_type.id, subject_type.id, object_type.id)
        )
