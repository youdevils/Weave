"""
The ChangeSet: the AI-facing description of proposed canonical model
changes, produced by the Planning stage of every Assisted workflow and
resolved/compiled entirely by OnyxJar (ai.services.resolution,
ai.services.staging). Replaces the old ChangePlan/EntityRef contract.

Semantic references, never canonical UUIDs. An existing entity is named by
its keys, as structured fields -- never a precomposed string the AI must copy
verbatim, and never a database id:

    TypeRef         {kind: existing, key}            | {kind: new, token}
    ObjectRef       {kind: existing, type_key, key}  | {kind: new, token}
    RelationshipRef {relationship_type_key, subject: ObjectRef, object: ObjectRef}
    AttributeRef    {owner_kind, owner_key, key}
    RuleRef         {relationship_type_key, subject_type_key, object_type_key}

A "new" token is an arbitrary string the AI chooses for an entity created in
this same ChangeSet so later actions can depend on it; OnyxJar alone mints
its real id and key. Keys of new entities are always OnyxJar-assigned (there
is no `key` field on any create action). Update/retire targets are
existing-only references, so "create then update the same new entity in one
ChangeSet" is unrepresentable by construction.

Every action carries an `action_id` so OnyxJar's deterministic feedback --
including model-wide cardinality failures on not-yet-real entities -- can
point at exactly the action that caused it.

v3 is a pure canonical mutation contract: references, values, lifecycle and
each action's own justification (`provenance` + `rationale`, which become the
Proposal's EvidenceReferences). It knows nothing about how an evidence
pipeline arrived at it -- Reconcile's links from actions back to evidence
claims and decisions live beside it, in ai.services.reconcile.compiler's
ChangeTrace, never inside it.

Shapes are closed and strict-structured-output compatible: a plain Union
(anyOf) of per-kind action models, each discriminated by its own `kind`
literal, and AttributeValue as a closed scalar union instead of `Any`.
"""

from __future__ import annotations

from typing import Literal, Optional, Union

from pydantic import BaseModel, Field

from ai.services.artifacts import Clarification, Finding, Interpretation, Provenance

TypeKind = Literal["object_type", "relationship_type"]
DataType = Literal["text", "number", "boolean", "date", "datetime", "choice", "url"]


# -- references ------------------------------------------------------------


class TypeRef(BaseModel):
    kind: Literal["existing", "new"]
    key: Optional[str] = None
    token: Optional[str] = None


class ObjectRef(BaseModel):
    kind: Literal["existing", "new"]
    type_key: Optional[str] = None
    key: Optional[str] = None
    token: Optional[str] = None


class RelationshipRef(BaseModel):
    relationship_type_key: str
    subject: ObjectRef
    object: ObjectRef


class AttributeRef(BaseModel):
    owner_kind: TypeKind
    owner_key: str
    key: str


class RuleRef(BaseModel):
    relationship_type_key: str
    subject_type_key: str
    object_type_key: str


class LifecycleTarget(BaseModel):
    """Exactly one of the per-entity fields is set, matching `entity`."""

    entity: Literal["object", "relationship", "object_type", "relationship_type", "attribute"]
    object: Optional[ObjectRef] = None
    relationship: Optional[RelationshipRef] = None
    type_key: Optional[str] = None
    attribute: Optional[AttributeRef] = None


# -- values ------------------------------------------------------------------


class AttributeValue(BaseModel):
    """
    One attribute value on an Object/Relationship. `key` names an existing
    AttributeDefinition of the entity's type; `attribute_token` instead names
    one created by a create_attribute action in this same ChangeSet (whose
    key OnyxJar has not assigned yet). Set exactly one of the *_value
    fields; none means an explicit null.
    """

    key: Optional[str] = None
    attribute_token: Optional[str] = None
    string_value: Optional[str] = None
    number_value: Optional[Union[int, float]] = None
    boolean_value: Optional[bool] = None

    def native(self):
        if self.boolean_value is not None:
            return self.boolean_value
        if self.number_value is not None:
            return self.number_value
        return self.string_value

    def set_variants(self) -> int:
        return sum(v is not None for v in (self.string_value, self.number_value, self.boolean_value))


class AttributeConfig(BaseModel):
    """AttributeDefinition.config by data_type (text: min_length/max_length;
    number: min/max; choice: choices). Unused keys stay null."""

    min_length: Optional[int] = None
    max_length: Optional[int] = None
    min: Optional[float] = None
    max: Optional[float] = None
    choices: Optional[list[str]] = None

    def to_dict(self) -> dict:
        return {key: value for key, value in self.model_dump().items() if value is not None}


class CardinalitySpec(BaseModel):
    minimum: int = 0
    maximum: Optional[int] = None


# -- actions -----------------------------------------------------------------


class _ActionBase(BaseModel):
    action_id: str
    rationale: str = ""
    # Verbatim support for this mutation, verified against the evidence by
    # the resolver and recorded as the Proposal's EvidenceReferences.
    provenance: list[Provenance] = Field(default_factory=list)


class CreateType(_ActionBase):
    kind: Literal["create_type"]
    type_kind: TypeKind
    token: str
    name: str
    description: str = ""


class UpdateType(_ActionBase):
    kind: Literal["update_type"]
    type_kind: TypeKind
    key: str
    name: Optional[str] = None
    description: Optional[str] = None


class CreateAttribute(_ActionBase):
    kind: Literal["create_attribute"]
    token: str
    owner_kind: TypeKind
    owner: TypeRef
    name: str
    data_type: DataType = "text"
    description: str = ""
    required: bool = False
    nullable: bool = True
    config: AttributeConfig = Field(default_factory=AttributeConfig)


class UpdateAttribute(_ActionBase):
    kind: Literal["update_attribute"]
    target: AttributeRef
    name: Optional[str] = None
    description: Optional[str] = None
    required: Optional[bool] = None
    nullable: Optional[bool] = None
    config: Optional[AttributeConfig] = None


class CreateRule(_ActionBase):
    kind: Literal["create_rule"]
    relationship_type: TypeRef
    subject_type: TypeRef
    object_type: TypeRef
    objects_per_subject: CardinalitySpec = Field(default_factory=CardinalitySpec)
    subjects_per_object: CardinalitySpec = Field(default_factory=CardinalitySpec)


class UpdateRule(_ActionBase):
    kind: Literal["update_rule"]
    target: RuleRef
    # The complete new cardinality (both sides), not a partial patch.
    objects_per_subject: CardinalitySpec
    subjects_per_object: CardinalitySpec


class CreateObject(_ActionBase):
    kind: Literal["create_object"]
    token: str
    type: TypeRef
    name: str
    description: str = ""
    attributes: list[AttributeValue] = Field(default_factory=list)
    # True only when an existing Object of this type with a matching name is
    # genuinely a different real-world entity (OnyxJar otherwise rejects the
    # create as a probable duplicate).
    confirmed_distinct: bool = False


class UpdateObject(_ActionBase):
    kind: Literal["update_object"]
    target: ObjectRef
    name: Optional[str] = None
    description: Optional[str] = None
    attributes: list[AttributeValue] = Field(default_factory=list)


class CreateRelationship(_ActionBase):
    kind: Literal["create_relationship"]
    relationship_type: TypeRef
    subject: ObjectRef
    object: ObjectRef
    attributes: list[AttributeValue] = Field(default_factory=list)
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None
    confirmed_distinct: bool = False


class UpdateRelationship(_ActionBase):
    kind: Literal["update_relationship"]
    target: RelationshipRef
    attributes: list[AttributeValue] = Field(default_factory=list)
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None


class SetActive(_ActionBase):
    """Retire (active=false) or reactivate (active=true) an existing entity."""

    kind: Literal["set_active"]
    target: LifecycleTarget
    active: bool


class Delete(_ActionBase):
    """Hard delete. Only operations whose policy allows it may use it;
    Reconcile maps removal evidence to set_active(false) instead."""

    kind: Literal["delete"]
    target: LifecycleTarget


ChangeAction = Union[
    CreateType,
    UpdateType,
    CreateAttribute,
    UpdateAttribute,
    CreateRule,
    UpdateRule,
    CreateObject,
    UpdateObject,
    CreateRelationship,
    UpdateRelationship,
    SetActive,
    Delete,
]

ALL_ACTION_KINDS = frozenset(
    {
        "create_type", "update_type", "create_attribute", "update_attribute", "create_rule",
        "update_rule", "create_object", "update_object", "create_relationship",
        "update_relationship", "set_active", "delete",
    }
)
SCHEMA_ACTION_KINDS = frozenset(
    {"create_type", "update_type", "create_attribute", "update_attribute", "create_rule", "update_rule"}
)
DATA_ACTION_KINDS = frozenset({"create_object", "update_object", "create_relationship", "update_relationship"})


class ChangeSet(BaseModel):
    schema_version: str = "3.0"
    summary: str = ""
    actions: list[ChangeAction] = Field(default_factory=list)


class PlanResult(BaseModel):
    """The literal response schema of a Planning-stage provider call."""

    schema_version: str = "3.0"
    interpretation: Interpretation = Field(default_factory=Interpretation)
    change_set: ChangeSet = Field(default_factory=ChangeSet)
    findings: list[Finding] = Field(default_factory=list)
    clarification: Clarification = Field(default_factory=Clarification)
