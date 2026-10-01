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

from typing import Any, Literal, Optional

from django.conf import settings
from pydantic import BaseModel, Field

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


class ChangeAction(BaseModel):
    operation: Literal["create", "update", "delete"]
    target_type: TargetType
    target_ref: EntityRef
    parent_ref: Optional[EntityRef] = None
    # Only meaningful (and required by validate_change_plan) when
    # target_type == "AttributeDefinition" -- see _IMPLIED_PARENT_DOMAIN.
    parent_type: Optional[Literal["ObjectType", "RelationshipType"]] = None
    fields: dict[str, Any] = Field(default_factory=dict)
    rationale: str = ""
    evidence: list[EvidenceItem] = Field(default_factory=list)

    def entity_refs_in_fields(self) -> list[tuple[str, EntityRef]]:
        """(field_key, EntityRef) pairs for every `fields` value that is an
        entity reference rather than a plain scalar, per entity_ref_fields_for."""
        refs = []
        for key in entity_ref_fields_for(self.target_type):
            if key not in self.fields:
                continue
            value = self.fields[key]
            if isinstance(value, EntityRef):
                refs.append((key, value))
            elif isinstance(value, dict):
                refs.append((key, EntityRef.model_validate(value)))
        return refs


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
