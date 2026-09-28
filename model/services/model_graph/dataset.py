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

        self._adjacency: dict[str, list[EffectiveRelationship]] = {oid: [] for oid in self.objects}
        for relationship in self.relationships.values():
            self._adjacency[relationship.source_id].append(relationship)
            if relationship.target_id != relationship.source_id:
                self._adjacency[relationship.target_id].append(relationship)

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
