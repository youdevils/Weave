"""
Compiles a validated semantic Change Plan into a normal OnyxJar Proposal.

compile_and_validate is the atomic commit-or-discard boundary (see its
docstring) that keeps every non-successful refinement attempt from ever
becoming a visible, capacity-consuming Proposal: it either commits a
complete, valid Proposal in one shot, or rolls back everything -- Proposal,
ProposalChanges, EvidenceReferences, and the speculative canonical writes --
together.

compile_change_plan itself only ever writes ProposalChange/EvidenceReference
rows (via the existing ProposalService/EvidenceService) -- it never touches
canonical tables, and never calls ProposalService.submit(). Creating a
Proposal through this module never modifies the canonical model.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from django.db import transaction

from model.models.model import Model
from model.models.proposal import Proposal, ProposalChange
from model.services.field_paths import ATTRIBUTE_FIELD_PREFIX
from model.services.proposal.evidence import EvidenceService
from model.services.proposal.proposal import ProposalService
from model.services.proposal.review import ProposalReviewService
from model.services.proposal.validation_runner import apply_and_validate
from model.services.validation.result import ValidationIssue

from ai.services.change_plan import ChangeAction, ChangePlan, EntityRef, entity_ref_fields_for

_IMPLIED_PARENT_TYPE = {
    "Object": "ObjectType",
    "Relationship": "RelationshipType",
    "RelationshipTypeRule": "RelationshipType",
}


class TempRefResolver:
    """
    Mints exactly one real uuid.uuid4() per distinct "new" temp token,
    memoised so every reference to that token across the whole Change Plan
    resolves to the same id. The AI never sees or chooses a real id for a
    new entity -- only OnyxJar, here, does.
    """

    def __init__(self):
        self._minted: dict[str, uuid.UUID] = {}

    def resolve(self, ref: EntityRef) -> uuid.UUID:
        if ref.kind == "existing":
            return uuid.UUID(str(ref.id))
        if ref.id not in self._minted:
            self._minted[ref.id] = uuid.uuid4()
        return self._minted[ref.id]


def _parent_type_for(action: ChangeAction) -> str:
    if action.parent_ref is None:
        return ""
    if action.target_type == "AttributeDefinition":
        return action.parent_type or ""
    return _IMPLIED_PARENT_TYPE.get(action.target_type, "")


def _resolve_field_value(action: ChangeAction, key: str, value, resolver: TempRefResolver):
    if key in entity_ref_fields_for(action.target_type):
        if isinstance(value, EntityRef):
            return str(resolver.resolve(value))
        if isinstance(value, dict):
            return str(resolver.resolve(EntityRef.model_validate(value)))
    return value


def _current_value(target_type: str, target_id, field_key: str):
    model_cls = ProposalReviewService.MODEL_MAP.get(target_type)
    if model_cls is None:
        return None
    instance = model_cls.objects.filter(id=target_id).first()
    if instance is None:
        return None
    if field_key.startswith(ATTRIBUTE_FIELD_PREFIX):
        key = field_key[len(ATTRIBUTE_FIELD_PREFIX):]
        attributes = getattr(instance, "attributes", None) or {}
        return attributes.get(key)
    return getattr(instance, field_key, None)


def compile_change_plan(*, model, user, change_plan: ChangePlan, proposal) -> list[ProposalChange]:
    """
    Resolves every EntityRef, fans each "update" ChangeAction out into one
    spec per touched field (the real apply machinery only supports one
    field per UPDATE ProposalChange row), and records the resulting specs
    via the existing ProposalService/EvidenceService. Never calls
    ProposalService.submit() -- the proposal stays WORKING.
    """

    resolver = TempRefResolver()
    specs: list[dict] = []
    action_ranges: list[tuple[ChangeAction, int, int]] = []

    for action in change_plan.actions:
        target_id = resolver.resolve(action.target_ref)
        parent_id = resolver.resolve(action.parent_ref) if action.parent_ref else None
        parent_type = _parent_type_for(action)
        start = len(specs)

        if action.operation == "create":
            after = {
                key: _resolve_field_value(action, key, value, resolver)
                for key, value in action.fields.items()
            }
            specs.append(
                {
                    "operation": ProposalChange.Operation.CREATE,
                    "target_type": action.target_type,
                    "target_id": target_id,
                    "parent_type": parent_type,
                    "parent_id": parent_id,
                    "before": None,
                    "after": after,
                }
            )

        elif action.operation == "update":
            for key, value in action.fields.items():
                resolved_value = _resolve_field_value(action, key, value, resolver)
                specs.append(
                    {
                        "operation": ProposalChange.Operation.UPDATE,
                        "target_type": action.target_type,
                        "target_id": target_id,
                        "parent_type": "",
                        "parent_id": None,
                        "before": {"field": key, "value": _current_value(action.target_type, target_id, key)},
                        "after": {"field": key, "value": resolved_value},
                    }
                )

        else:  # delete -- fields are not meaningful for a delete
            specs.append(
                {
                    "operation": ProposalChange.Operation.DELETE,
                    "target_type": action.target_type,
                    "target_id": target_id,
                    "parent_type": "",
                    "parent_id": None,
                    "before": None,
                    "after": None,
                }
            )

        action_ranges.append((action, start, len(specs)))

    created = ProposalService.record_changes_bulk(proposal=proposal, specs=specs)

    # Level B rationale/evidence: attach per-action, to every ProposalChange
    # that action fanned out into. Coexists with (does not replace) any
    # explicit evidence items the action carries.
    for action, start, end in action_ranges:
        change_ids = [created[i].id for i in range(start, end)]
        if not change_ids:
            continue
        if action.rationale.strip():
            EvidenceService.add_for_changes(proposal, change_ids, "AI", "", action.rationale.strip())
        for item in action.evidence:
            EvidenceService.add_for_changes(proposal, change_ids, item.source, item.locator, item.note)

    return created


@dataclass
class CompileResult:
    proposal: Proposal | None  # None if the attempt was invalid -- nothing was kept
    issues: list[ValidationIssue]


def compile_and_validate(*, model, user, operation, change_plan: ChangePlan) -> CompileResult:
    """
    One atomic attempt. If compile_change_plan itself raises (e.g. an
    EvidenceService cap violation, or any other unexpected error), Django's
    atomic block rolls back everything written so far automatically and the
    exception propagates to the caller -- this function does not need to
    special-case that; it is exactly the guarantee transaction.atomic()
    always gives.
    """

    with transaction.atomic():
        proposal = ProposalService.create_working(
            model,
            user,
            source=Proposal.Source.AI,
            title=f"Assisted: {operation.name}"[:200],
            # Level A rationale: the Change Plan's overall explanation maps
            # onto the existing Proposal-level "Change note" field.
            summary=change_plan.summary,
        )  # re-checks PROPOSAL_MAX_LIVE_PER_MODEL capacity at this point, authoritatively

        compile_change_plan(model=model, user=user, change_plan=change_plan, proposal=proposal)

        locked_model = Model.objects.select_for_update().get(pk=model.pk)

        with transaction.atomic():  # nested -> a SAVEPOINT, not a new transaction
            outcome = apply_and_validate(locked_model, proposal)
            transaction.set_rollback(True)  # always discard the speculative canonical writes

        if outcome.issues:
            transaction.set_rollback(True)  # rolls back the WHOLE outer block too
            return CompileResult(proposal=None, issues=outcome.issues)

        return CompileResult(proposal=proposal, issues=[])
        # falling through lets the outer `with transaction.atomic()` commit
        # normally -- proposal + its ProposalChanges + EvidenceReferences
        # become real and visible.
