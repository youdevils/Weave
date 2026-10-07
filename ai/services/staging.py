"""
Speculative staging and final commit of a resolved ChangeSet (replaces
ai.services.proposal_compiler).

Both go through the one real apply-and-validate implementation
(model.services.proposal.validation_runner.apply_and_validate), against
canonical state as it stands at that instant:

    stage_and_validate  -- ALWAYS rolls back. Builds a throwaway WORKING
                           Proposal, applies it inside a savepoint, runs full
                           model validation and, when clean, captures the
                           ProjectedDelta (the semantic before/after of every
                           touched entity) before discarding everything.
                           Nothing -- Proposal, ProposalChange,
                           EvidenceReference or canonical row -- survives.
                           This is the speculative state Verification reviews;
                           it never becomes canonical because a stage accepted
                           it.
    commit_proposal     -- the final deterministic gate, run only after
                           Verification approves: the same atomic
                           commit-or-discard boundary the old compiler had.
                           Keeps a complete, valid WORKING Proposal (never
                           canonical rows) or nothing at all.

Neither ever calls ProposalService.submit(): acceptance stays human.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from django.db import transaction
from pydantic import BaseModel, Field

from model.models.model import Model
from model.models.proposal import Proposal
from model.services.proposal.evidence import CHANGE_NOTE_MAX_LENGTH, EvidenceService
from model.services.proposal.proposal import ProposalService
from model.services.proposal.validation_runner import apply_and_validate

from ai.services.resolution import Resolution
from ai.services.semantic.catalogue import (
    catalogue_attribute,
    catalogue_object_type,
    catalogue_relationship_type,
    catalogue_rule,
)
from ai.services.semantic.index import SemanticModelIndex
from ai.services.semantic.records import RelationshipRecord, object_record, relationship_record

_RELATED_RELATIONSHIPS_LIMIT = 200

_ENTITY_BY_TARGET_TYPE = {
    "ObjectType": "object_type",
    "RelationshipType": "relationship_type",
    "AttributeDefinition": "attribute",
    "RelationshipTypeRule": "rule",
    "Object": "object",
    "Relationship": "relationship",
}


class DeltaEntry(BaseModel):
    entity: str
    change: str  # created | updated | retired | reactivated | deleted (comma-joined if several)
    action_ids: list[str] = Field(default_factory=list)
    before: Optional[dict] = None
    after: Optional[dict] = None


class ProjectedDelta(BaseModel):
    """The speculative result of applying a ChangeSet, semantically described."""

    entries: list[DeltaEntry] = Field(default_factory=list)
    # Post-apply relationships touching any touched Object, for context.
    related_relationships: list[RelationshipRecord] = Field(default_factory=list)


@dataclass
class StagedResult:
    issues: list  # model.services.validation.result.ValidationIssue
    delta: ProjectedDelta | None


@dataclass
class CommitResult:
    proposal: Proposal | None  # None if invalid (or no longer wanted) -- nothing was kept
    issues: list


def entity_record(index: SemanticModelIndex, target_type: str, target_id) -> dict | None:
    target_id = str(target_id)
    if target_type == "ObjectType":
        item = index.object_types.get(target_id)
        return catalogue_object_type(index, item).model_dump() if item else None
    if target_type == "RelationshipType":
        item = index.relationship_types.get(target_id)
        return catalogue_relationship_type(index, item).model_dump() if item else None
    if target_type == "AttributeDefinition":
        item = index.attributes.get(target_id)
        owner = index.type_by_id(item.owner_id) if item else None
        if not owner:
            return None
        return {"owner_kind": item.owner_kind, "owner_key": owner.key, **catalogue_attribute(item).model_dump()}
    if target_type == "RelationshipTypeRule":
        item = index.rules.get(target_id)
        if not item:
            return None
        return {
            "relationship_type_key": index.relationship_types[item.relationship_type_id].key,
            **catalogue_rule(index, item).model_dump(),
        }
    if target_type == "Object":
        item = index.objects.get(target_id)
        return object_record(index, item).model_dump() if item else None
    if target_type == "Relationship":
        item = index.relationships.get(target_id)
        return relationship_record(index, item).model_dump() if item else None
    return None


def build_projected_delta(before: SemanticModelIndex, after: SemanticModelIndex, resolution: Resolution) -> ProjectedDelta:
    grouped: dict[tuple[str, str], dict] = {}
    for touched in resolution.touched:
        slot = grouped.setdefault(
            (touched.target_type, touched.target_id), {"changes": [], "action_ids": []}
        )
        if touched.change not in slot["changes"]:
            slot["changes"].append(touched.change)
        if touched.action_id not in slot["action_ids"]:
            slot["action_ids"].append(touched.action_id)

    entries = []
    touched_objects = set()
    touched_relationships = set()
    for (target_type, target_id), slot in grouped.items():
        entries.append(
            DeltaEntry(
                entity=_ENTITY_BY_TARGET_TYPE.get(target_type, target_type),
                change=",".join(slot["changes"]),
                action_ids=slot["action_ids"],
                before=entity_record(before, target_type, target_id),
                after=entity_record(after, target_type, target_id),
            )
        )
        if target_type == "Object":
            touched_objects.add(target_id)
        elif target_type == "Relationship":
            touched_relationships.add(target_id)
            relationship = after.relationships.get(target_id)
            if relationship is not None:
                touched_objects.update({relationship.subject_id, relationship.object_id})

    related = []
    seen = set(touched_relationships)
    for object_id in sorted(touched_objects):
        for relationship in after.relationships_of(object_id):
            if relationship.id in seen or not relationship.is_active:
                continue
            seen.add(relationship.id)
            related.append(relationship_record(after, relationship))
            if len(related) >= _RELATED_RELATIONSHIPS_LIMIT:
                break

    return ProjectedDelta(entries=entries, related_relationships=related)


def record_resolved(proposal, resolution: Resolution) -> None:
    """Writes the resolved specs and their evidence onto `proposal` (ProposalChange/
    EvidenceReference rows only -- never canonical tables)."""

    created = ProposalService.record_changes_bulk(proposal=proposal, specs=resolution.specs)
    for action_id, start, end in resolution.action_ranges:
        change_ids = [created[i].id for i in range(start, end)]
        for source, locator, note in resolution.evidence.get(action_id, []):
            EvidenceService.add_for_changes(proposal, change_ids, source, locator, note)


def _title(operation) -> str:
    return f"Assisted: {operation.name}"[:200]


def stage_and_validate(*, model, user, operation, resolution: Resolution, index: SemanticModelIndex) -> StagedResult:
    delta = None
    with transaction.atomic():
        proposal = ProposalService.create_working(model, user, source=Proposal.Source.AI, title=_title(operation))
        record_resolved(proposal, resolution)
        locked_model = Model.objects.select_for_update().get(pk=model.pk)
        outcome = apply_and_validate(locked_model, proposal)
        if not outcome.issues:
            delta = build_projected_delta(index, SemanticModelIndex.load(locked_model), resolution)
        transaction.set_rollback(True)  # always: staging never keeps anything
    return StagedResult(issues=outcome.issues, delta=delta)


def commit_proposal(
    *,
    model,
    user,
    operation,
    resolution: Resolution,
    summary: str,
    should_commit: Callable[[], bool] | None = None,
) -> CommitResult:
    """
    `should_commit` is called inside the commit transaction, before anything
    is written: the caller (assisted.services.execution) uses it to re-check,
    under a row lock, that its AssistedTask is still the one running -- so a
    task that was meanwhile reclaimed as stale can never leave an orphaned
    Proposal behind.
    """

    with transaction.atomic():
        # Model row first, then should_commit's own lock: the same lock order
        # assisted.services.lifecycle._reclaim_stale uses (Model, then its
        # AssistedTasks), so the two can never deadlock each other.
        locked_model = Model.objects.select_for_update().get(pk=model.pk)
        if should_commit is not None and not should_commit():
            transaction.set_rollback(True)
            return CommitResult(proposal=None, issues=[])

        proposal = ProposalService.create_working(
            model,
            user,
            source=Proposal.Source.AI,
            title=_title(operation),
            summary=(summary or "")[:CHANGE_NOTE_MAX_LENGTH],
        )  # re-checks PROPOSAL_MAX_LIVE_PER_MODEL capacity at this point, authoritatively
        record_resolved(proposal, resolution)

        with transaction.atomic():  # nested -> a SAVEPOINT
            outcome = apply_and_validate(locked_model, proposal)
            transaction.set_rollback(True)  # always discard the speculative canonical writes

        if outcome.issues:
            transaction.set_rollback(True)  # rolls back the WHOLE outer block too
            return CommitResult(proposal=None, issues=outcome.issues)

        return CommitResult(proposal=proposal, issues=[])
