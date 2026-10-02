"""
The semantic Change Plan: the AI's structured, bounded description of
proposed canonical changes, and OnyxJar's deterministic (never LLM-dependent)
validation of its references before anything is compiled into a Proposal.

Change Plan vocabulary maps closely onto model.services.proposal.proposal's
record_changes_bulk spec shape (operation/target_type/target_id/parent_type/
parent_id/before/after) -- see ai.services.proposal_compiler for the mapping
-- but is intentionally its own, separate contract: the AI never sees or
produces a ProposalChange directly.

Existing entities are referenced by their real, stable OnyxJar id (an
EntityRef with kind="existing"). New entities -- not yet in the canonical
model -- are referenced by an arbitrary temporary token (kind="new") that
only has meaning within this one Change Plan, so other actions in the same
plan can point at an entity that doesn't exist yet. OnyxJar (the Proposal
Compiler), not the AI, is the only thing that ever mints the real id a "new"
token will become.

Phase 1 deliberately keeps this bounded: a "new" token may be the target_ref
of at most one action (a "create"), never also later "update"d within the
same plan -- the existing Proposal apply machinery has no race-free way to
create and then update the same not-yet-real target in one proposal (apply
order is grouped by target type, not guaranteed create-before-update for two
changes addressing the same target_id). If the AI needs specific field
values on a newly created entity, they belong directly in that entity's own
"create" action's `fields`.
"""

from __future__ import annotations

from typing import Literal, Optional

from django.conf import settings
from pydantic import BaseModel, Field, field_validator, model_validator

from model.services.field_paths import ATTRIBUTE_FIELD_PREFIX

TargetType = Literal[
    "ObjectType",
    "RelationshipType",
    "AttributeDefinition",
    "RelationshipTypeRule",
    "Object",
    "Relationship",
]

# Which `fields` keys hold entity references (rather than plain scalar
# values) for a given target_type -- mirrors the parent/endpoint linkage
# model.services.proposal.submission._create_kwargs already uses.
RELATIONSHIP_ENDPOINT_FIELDS = ("subject_id", "object_id")
RELATIONSHIP_TYPE_RULE_ENDPOINT_FIELDS = ("subject_type_id", "object_type_id")

_ENTITY_REF_FIELDS_BY_TARGET_TYPE: dict[str, tuple[str, ...]] = {
    "Relationship": RELATIONSHIP_ENDPOINT_FIELDS,
    "RelationshipTypeRule": RELATIONSHIP_TYPE_RULE_ENDPOINT_FIELDS,
}

# AI-facing field names for the same two endpoint pairs above, mapped to
# their internal/compiler names. The AI is taught (see
# ai.services.orchestrator._system_prompt) to use these "_ref" names instead
# of the "_id" ones -- a field holding an EntityRef should never look like a
# raw database column -- but every downstream consumer (fields_dict(),
# entity_refs_in_fields(), model.services.entity_fields.illegal_fields(), the
# compiler) still only ever sees the internal name, since ChangeAction
# rewrites it immediately below (_normalize_ai_facing_field_keys).
_AI_FACING_FIELD_ALIASES: dict[str, dict[str, str]] = {
    "Relationship": {"subject_ref": "subject_id", "object_ref": "object_id"},
    "RelationshipTypeRule": {
        "subject_type_ref": "subject_type_id",
        "object_type_ref": "object_type_id",
    },
}

# Every other target type's parent type is implied by the target type itself
# (an Object's parent is always an ObjectType, a Relationship's/
# RelationshipTypeRule's is always a RelationshipType) -- only
# AttributeDefinition's parent is ambiguous (it may belong to either), so
# only it carries an explicit parent_type.
_IMPLIED_PARENT_DOMAIN: dict[str, str] = {
    "Object": "object_type",
    "Relationship": "relationship_type",
    "RelationshipTypeRule": "relationship_type",
}

_TARGET_DOMAIN: dict[str, str] = {
    "Object": "object",
    "Relationship": "relationship",
    "ObjectType": "object_type",
    "RelationshipType": "relationship_type",
    # Not modelled as directly addressable entities in EffectiveDataset --
    # existence of these two is left to the real Proposal validation/apply
    # pipeline (which does check them, against real DB rows) rather than
    # this deterministic pre-check. A documented Phase 1 boundary, not an
    # oversight.
    "AttributeDefinition": "unverifiable",
    "RelationshipTypeRule": "unverifiable",
}


def entity_ref_fields_for(target_type: str) -> tuple[str, ...]:
    return _ENTITY_REF_FIELDS_BY_TARGET_TYPE.get(target_type, ())


class EntityRef(BaseModel):
    kind: Literal["existing", "new"]
    id: str


class EvidenceItem(BaseModel):
    source: str
    locator: str = ""
    note: str = ""


class UnresolvedIssue(BaseModel):
    code: str
    message: str
    target_ref: Optional[EntityRef] = None


class AttributeDefinitionConfig(BaseModel):
    """
    AttributeDefinition.config's validation settings, by data_type -- see
    model.models.attribute_definition.AttributeDefinition.clean. Which keys
    are meaningful depends on the attribute's data_type (text: min_length/
    max_length; number: min/max; choice: choices); the rest stay null. A
    bounded, explicit stand-in for what was a second free-form nested dict
    one level inside `fields` -- the same Structured Outputs problem as
    `fields` itself (see FieldValue below), so it gets the same treatment
    rather than being left as an escape hatch back into `Any`.
    """

    min_length: Optional[int] = None
    max_length: Optional[int] = None
    min: Optional[float] = None
    max: Optional[float] = None
    choices: Optional[list[str]] = None

    def to_dict(self) -> dict:
        return {key: value for key, value in self.model_dump().items() if value is not None}


class FieldValue(BaseModel):
    """
    One value a ChangeAction field may hold. OpenAI Structured Outputs'
    strict mode has no way to represent a truly free-form value -- every
    object must declare `additionalProperties: false` and a closed set of
    properties, which is exactly what `Any`/a bare dict cannot do -- so
    this is the closed set of shapes a field value has ever actually
    needed: a plain string (covers TEXT, DATE, DATETIME, CHOICE and URL
    attribute values, which are all string-typed per
    model.services.validation.attributes.validate_attribute_value), a
    number, a boolean, a reference to another entity (a relationship
    endpoint or an AttributeDefinition's parent), or an AttributeDefinition's
    own nested validation config. The AI sets exactly one; `native()`
    returns the one Python value this FieldValue actually represents, in
    the same shape `fields` has always carried downstream.
    """

    string_value: Optional[str] = None
    number_value: Optional[float] = None
    boolean_value: Optional[bool] = None
    entity_ref_value: Optional[EntityRef] = None
    config_value: Optional[AttributeDefinitionConfig] = None

    def native(self):
        if self.entity_ref_value is not None:
            return self.entity_ref_value
        if self.config_value is not None:
            return self.config_value.to_dict()
        if self.boolean_value is not None:
            return self.boolean_value
        if self.number_value is not None:
            return self.number_value
        if self.string_value is not None:
            return self.string_value
        return None

    @classmethod
    def of(cls, value) -> "FieldValue":
        """
        Builds a FieldValue from a plain Python value -- the shorthand
        ChangeAction accepts for `fields` at construction time (see its
        field_validator just below), which is what every existing
        test/fixture in this codebase already passes as a plain dict.
        """

        if isinstance(value, FieldValue):
            return value
        if isinstance(value, EntityRef):
            return cls(entity_ref_value=value)
        if isinstance(value, AttributeDefinitionConfig):
            return cls(config_value=value)
        if isinstance(value, dict):
            if {"kind", "id"} <= value.keys():
                return cls(entity_ref_value=EntityRef.model_validate(value))
            return cls(config_value=AttributeDefinitionConfig.model_validate(value))
        if isinstance(value, bool):
            return cls(boolean_value=value)
        if isinstance(value, (int, float)):
            return cls(number_value=float(value))
        if value is None:
            return cls()
        return cls(string_value=str(value))


class FieldEntry(BaseModel):
    key: str
    value: FieldValue


class ChangeAction(BaseModel):
    operation: Literal["create", "update", "delete"]
    target_type: TargetType
    target_ref: EntityRef
    parent_ref: Optional[EntityRef] = None
    # Only meaningful (and required by validate_change_plan) when
    # target_type == "AttributeDefinition" -- see _IMPLIED_PARENT_DOMAIN.
    parent_type: Optional[Literal["ObjectType", "RelationshipType"]] = None
    # A list of (key, value) pairs, not dict[str, Any]/a bare dict -- see
    # FieldValue's docstring. A key addressing an Object/Relationship's own
    # dynamic, per-ObjectType-defined attribute (the one place a field's
    # *key* truly cannot be enumerated ahead of time) uses the same
    # "attributes.<key>" dotted convention model.services.field_paths
    # already defines for field-level attribute updates -- see
    # fields_dict() below.
    fields: list[FieldEntry] = Field(default_factory=list)
    rationale: str = ""
    evidence: list[EvidenceItem] = Field(default_factory=list)

    @field_validator("fields", mode="before")
    @classmethod
    def _coerce_fields(cls, value):
        """
        Accepts the historical dict shorthand ({"name": "X"}) this
        codebase's own tests and fixtures already use, converting it to the
        explicit list[FieldEntry] shape the actual schema -- and what a real
        OpenAI structured-output response always arrives as -- requires.
        Anything already list-shaped (dicts or FieldEntry instances) passes
        through unchanged, item by item.
        """

        if isinstance(value, dict):
            return [{"key": key, "value": FieldValue.of(raw)} for key, raw in value.items()]
        return value

    @model_validator(mode="after")
    def _normalize_ai_facing_field_keys(self) -> "ChangeAction":
        """
        Rewrites any AI-facing alias key (see _AI_FACING_FIELD_ALIASES) to
        its internal name, in place. Deliberately never raises here, even on
        a collision with an already-present internal key -- a Pydantic
        error at this point (i.e. while OpenAIProvider.generate_structured's
        client.responses.parse(...) is building this model from the
        provider's response) would surface as a hard FAILED run, not a
        validate_change_plan issue, bypassing the whole refinement loop.
        Rule 10 in validate_change_plan catches a resulting duplicate key
        the same structured way as every other semantic defect instead.
        """

        aliases = _AI_FACING_FIELD_ALIASES.get(self.target_type)
        if not aliases:
            return self
        for entry in self.fields:
            internal_key = aliases.get(entry.key)
            if internal_key is not None:
                entry.key = internal_key
        return self

    def fields_dict(self) -> dict:
        """
        Reconstructs the plain {key: native_value} mapping the rest of the
        compiler has always worked with for a CREATE action's single
        combined `after` payload, nesting any "attributes.<key>" entries
        into one "attributes" sub-dict -- exactly the shape
        Object.objects.create(**after) (model.services.proposal.submission)
        expects. Only meaningful for CREATE: an UPDATE processes `fields`
        entry-by-entry instead (see ai.services.proposal_compiler), since
        each entry is its own independent field-level change and must not
        be merged with any other.
        """

        result: dict = {}
        attributes: dict = {}

        for entry in self.fields:
            native = entry.value.native()
            if entry.key.startswith(ATTRIBUTE_FIELD_PREFIX):
                attributes[entry.key[len(ATTRIBUTE_FIELD_PREFIX):]] = native
            else:
                result[entry.key] = native

        if attributes:
            result["attributes"] = attributes

        return result

    def entity_refs_in_fields(self) -> list[tuple[str, EntityRef]]:
        """(field_key, EntityRef) pairs for every `fields` entry that is an
        entity reference rather than a plain scalar, per entity_ref_fields_for."""
        allowed = entity_ref_fields_for(self.target_type)
        return [
            (entry.key, entry.value.entity_ref_value)
            for entry in self.fields
            if entry.key in allowed and entry.value.entity_ref_value is not None
        ]


class ChangePlan(BaseModel):
    schema_version: str = "1.0"
    summary: str = ""
    actions: list[ChangeAction] = Field(default_factory=list)


def _issue(code: str, message: str, ref: Optional[EntityRef] = None) -> UnresolvedIssue:
    return UnresolvedIssue(code=code, message=message, target_ref=ref)


def _resolves_in_domain(domain: str, ref_id: str, dataset) -> bool:
    if domain == "object":
        return dataset.object(ref_id) is not None
    if domain == "relationship":
        return dataset.relationship(ref_id) is not None
    if domain == "object_type":
        return dataset.object_type(ref_id) is not None
    if domain == "relationship_type":
        return dataset.relationship_type(ref_id) is not None
    return True  # "unverifiable" -- not flagged here, see _TARGET_DOMAIN docstring


def validate_change_plan(plan: ChangePlan, dataset) -> list[UnresolvedIssue]:
    """
    Deterministic, LLM-independent validation of a Change Plan's references
    and operation/kind shape -- run before anything is compiled into a
    Proposal. `dataset` is always a canonical-only EffectiveDataset
    (load_effective_dataset(model, proposal=None)); existing entities are
    never resolved against an in-progress AI candidate (there isn't one --
    see ai.services.proposal_compiler.compile_and_validate).
    """

    issues: list[UnresolvedIssue] = []

    if len(plan.actions) > settings.AI_MAX_CHANGE_PLAN_ACTIONS:
        issues.append(
            _issue(
                "change_plan_too_large",
                f"A Change Plan may contain at most "
                f"{settings.AI_MAX_CHANGE_PLAN_ACTIONS} actions.",
            )
        )

    new_token_definitions: dict[str, list[int]] = {}
    new_token_other_targets: dict[str, list[int]] = {}
    referenced_new_tokens: set[str] = set()

    for index, action in enumerate(plan.actions):
        # Rules 1-3: operation/kind matching.
        if action.operation == "create" and action.target_ref.kind != "new":
            issues.append(
                _issue(
                    "create_requires_new_target_ref",
                    "A 'create' action's target_ref must be kind='new'.",
                    action.target_ref,
                )
            )
        elif action.operation in ("update", "delete") and action.target_ref.kind != "existing":
            issues.append(
                _issue(
                    f"{action.operation}_requires_existing_target_ref",
                    f"A '{action.operation}' action's target_ref must be kind='existing'.",
                    action.target_ref,
                )
            )

        if action.operation == "update" and not action.fields:
            issues.append(
                _issue(
                    "update_requires_at_least_one_field",
                    "An 'update' action must specify at least one field to change.",
                    action.target_ref,
                )
            )

        # Track every action whose target_ref is a given "new" token, split
        # into its one allowed defining create (rule 5) vs. any other action
        # retargeting the same token (rule 6).
        if action.target_ref.kind == "new":
            if action.operation == "create":
                new_token_definitions.setdefault(action.target_ref.id, []).append(index)
            else:
                new_token_other_targets.setdefault(action.target_ref.id, []).append(index)

        # Rule 4: every "existing" ref anywhere in the action must resolve
        # against canonical state (where EffectiveDataset can verify it).
        if action.target_ref.kind == "existing":
            domain = _TARGET_DOMAIN.get(action.target_type, "unverifiable")
            if not _resolves_in_domain(domain, action.target_ref.id, dataset):
                issues.append(
                    _issue(
                        "unresolvable_existing_reference",
                        f"No {action.target_type} with id '{action.target_ref.id}' exists.",
                        action.target_ref,
                    )
                )

        if action.parent_ref is not None:
            if action.target_type == "AttributeDefinition":
                parent_domain = (
                    "object_type" if action.parent_type == "ObjectType" else "relationship_type"
                )
                if action.parent_type is None:
                    issues.append(
                        _issue(
                            "attribute_definition_requires_parent_type",
                            "An AttributeDefinition action must declare parent_type "
                            "('ObjectType' or 'RelationshipType').",
                            action.parent_ref,
                        )
                    )
            else:
                parent_domain = _IMPLIED_PARENT_DOMAIN.get(action.target_type, "unverifiable")

            if action.parent_ref.kind == "new":
                referenced_new_tokens.add(action.parent_ref.id)
            elif not _resolves_in_domain(parent_domain, action.parent_ref.id, dataset):
                issues.append(
                    _issue(
                        "unresolvable_existing_reference",
                        f"No parent entity with id '{action.parent_ref.id}' exists.",
                        action.parent_ref,
                    )
                )

        for _key, ref in action.entity_refs_in_fields():
            if ref.kind == "new":
                referenced_new_tokens.add(ref.id)
                continue
            field_domain = "object" if action.target_type == "Relationship" else "object_type"
            if not _resolves_in_domain(field_domain, ref.id, dataset):
                issues.append(
                    _issue(
                        "unresolvable_existing_reference",
                        f"No entity with id '{ref.id}' exists.",
                        ref,
                    )
                )

        # Rules 7-10: FieldValue kind/shape checks -- iterate action.fields
        # directly, not via entity_refs_in_fields() above (which only ever
        # surfaces *well-formed* refs for the existing-reference check and
        # would silently skip exactly the malformed entries these rules
        # exist to catch).
        ref_keys = entity_ref_fields_for(action.target_type)
        seen_keys: dict[str, int] = {}
        for entry in action.fields:
            seen_keys[entry.key] = seen_keys.get(entry.key, 0) + 1

            set_variants = sum(
                1
                for value in (
                    entry.value.string_value,
                    entry.value.number_value,
                    entry.value.boolean_value,
                    entry.value.entity_ref_value,
                    entry.value.config_value,
                )
                if value is not None
            )
            if set_variants > 1:
                issues.append(
                    _issue(
                        "ambiguous_field_value",
                        f"Field '{entry.key}' on this {action.target_type} sets more "
                        "than one kind of value at once; it must set exactly one.",
                        action.target_ref,
                    )
                )

            if entry.key in ref_keys and entry.value.entity_ref_value is None:
                issues.append(
                    _issue(
                        "entity_reference_required",
                        f"Field '{entry.key}' on this {action.target_type} must be an "
                        "entity reference ({\"kind\": \"existing\"|\"new\", \"id\": ...}), "
                        "not a plain value.",
                        action.target_ref,
                    )
                )
            elif entry.key not in ref_keys and entry.value.entity_ref_value is not None:
                issues.append(
                    _issue(
                        "unexpected_entity_reference",
                        f"Field '{entry.key}' on this {action.target_type} is a plain "
                        "value field, not an entity reference.",
                        action.target_ref,
                    )
                )

        for key, count in seen_keys.items():
            if count > 1:
                issues.append(
                    _issue(
                        "duplicate_field_key",
                        f"Field '{key}' is set more than once on this {action.target_type} action.",
                        action.target_ref,
                    )
                )

    # Rule 5: every referenced "new" token must be defined by exactly one
    # create action in this plan.
    for token in referenced_new_tokens:
        definitions = new_token_definitions.get(token, [])
        if len(definitions) == 0:
            issues.append(
                _issue(
                    "dangling_temp_reference",
                    f"Temporary reference '{token}' is used but never created in this plan.",
                    EntityRef(kind="new", id=token),
                )
            )

    # Rule 6: a "new" token may never also be the target_ref of a later
    # (non-create) action in the same plan.
    for token, indices in new_token_other_targets.items():
        issues.append(
            _issue(
                "unsupported_same_plan_update_of_new_entity",
                f"Temporary reference '{token}' cannot be updated within the same "
                "Change Plan that creates it -- put the desired values directly "
                "in its 'create' action's fields.",
                EntityRef(kind="new", id=token),
            )
        )

    return issues
