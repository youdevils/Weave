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
from model.services import entity_fields, keys
from model.services.field_paths import ATTRIBUTE_FIELD_PREFIX
from model.services.model_graph.loader import load_effective_dataset
from model.services.proposal.evidence import EvidenceService
from model.services.proposal.proposal import ProposalService
from model.services.proposal.review import ProposalReviewService
from model.services.proposal.validation_runner import apply_and_validate
from model.services.validation.result import ValidationIssue

from ai.services.change_plan import (
    ChangeAction,
    ChangePlan,
    EntityRef,
    field_ref_domain,
    parent_domain,
    target_domain,
)

_IMPLIED_PARENT_TYPE = {
    "Object": "ObjectType",
    "Relationship": "RelationshipType",
    "RelationshipTypeRule": "RelationshipType",
}

# ObjectType/RelationshipType are top-level: their parent is the Model
# itself, which never appears as a parent_ref (Model isn't part of the
# Change Plan's EntityRef graph -- there's no "new"/"existing" token for
# it). model/views/common_context.py's working-overlay builders
# (_build_working_object_types/_build_working_relationship_types) only
# recognise a CREATE as proposal-only when parent_type == "Model", the
# same literal every editor-driven CREATE already stamps (see e.g.
# model/views/object_type_editor.py's record_change calls) -- so these
# two target types must resolve to "Model" regardless of parent_ref.
_MODEL_SCOPED_TARGET_TYPES = frozenset({"ObjectType", "RelationshipType"})


class ChangePlanCompilationError(Exception):
    """
    Base for a deterministic, per-action compile-time defect that must
    become a ValidationIssue (refinement feedback) rather than propagate
    as a raw exception -- the same "turn a crash into retryable feedback"
    shape every subclass shares; each knows how to describe itself.
    """

    def issue(self) -> ValidationIssue:
        raise NotImplementedError


class InvalidFieldError(ChangePlanCompilationError):
    """
    Raised when a CREATE/UPDATE action supplies a `fields` key that is not
    a real, settable field for its target_type -- e.g. `to`/`from` on a
    RelationshipType, which carries no endpoint fields at all (those live
    on a separate RelationshipTypeRule action instead -- see
    model.services.entity_fields). Collects every illegal key for the
    action in one pass, not just the first, so the AI gets one complete
    refinement signal per action rather than discovering N bad keys one
    refinement cycle at a time.
    """

    def __init__(self, *, target_type: str, target_id, field_names: list[str]):
        names = ", ".join(sorted(field_names))
        super().__init__(f"{target_type} has no field(s): {names}.")
        self.target_type = target_type
        self.target_id = target_id
        self.field_names = list(field_names)

    def issue(self) -> ValidationIssue:
        names = ", ".join(sorted(self.field_names))
        hint = (
            " Endpoint/cardinality information belongs on a separate "
            "RelationshipTypeRule action parented to this RelationshipType, "
            "not on the RelationshipType itself."
            if self.target_type == "RelationshipType"
            else ""
        )
        return ValidationIssue(
            code="invalid_field",
            field=self.field_names[0] if len(self.field_names) == 1 else None,
            message=f"{self.target_type} has no field(s): {names}.{hint}",
            target_type=self.target_type,
            target_id=self.target_id,
        )


def _assign_key(model, proposal, action: ChangeAction, parent_type, parent_id, after: dict, claimed: dict) -> None:
    """
    CREATE-only. Always assigns after["key"] from after["name"] via
    model.services.keys -- keys are fully automatic, so any key a Change
    Plan action supplied is discarded and overwritten here, never trusted
    (the AI should never be instructed to invent one, and a Change Plan
    that does supply one is still not trusted, for the same reason a
    human-typed key never is).

    `claimed` tracks keys already assigned to earlier CREATE actions of
    the same (target_type, parent_type, parent_id) within THIS SAME
    change plan: compile_change_plan only records changes to the
    proposal in one batch at the very end (record_changes_bulk), so
    keys.claimed_keys_in_proposal has no visibility yet into sibling
    in-progress actions -- this dict is that visibility.
    """

    scope_key = (action.target_type, parent_type, parent_id)
    also_used = claimed.setdefault(scope_key, set())

    generated = keys.generate_key(
        action.target_type,
        after.get("name") or "",
        model=model,
        proposal=proposal,
        parent_type=parent_type,
        parent_id=parent_id,
        also_used=also_used,
    )

    after["key"] = generated
    also_used.add(generated)


_KEY_LOOKUP = {
    "object_type": lambda dataset, key: dataset.object_type_by_key(key),
    "relationship_type": lambda dataset, key: dataset.relationship_type_by_key(key),
    "object": lambda dataset, key: dataset.object_by_key(key),
    "attribute_definition": lambda dataset, key: dataset.attribute_definition_by_key(key),
    "relationship_type_rule": lambda dataset, key: dataset.relationship_type_rule_by_key(key),
}


class UnresolvableKeyError(ChangePlanCompilationError):
    """
    An "existing"-kind EntityRef's key/key-path doesn't resolve against the
    canonical dataset. validate_change_plan's own rule 4 already guarantees
    this never fires in practice (it checks every existing-ref against the
    same dataset shape moments earlier, in the same request) -- this is a
    defensive backstop against the narrow window between that check and
    this compile attempt, not the primary gate.
    """

    def __init__(self, *, domain: str, key: str):
        super().__init__(f"No {domain} with key '{key}' exists.")
        self.domain = domain
        self.key = key

    def issue(self) -> ValidationIssue:
        return ValidationIssue(code="unresolvable_existing_reference", message=str(self))


class TempRefResolver:
    """
    Resolves every EntityRef to a real uuid.UUID: for "new" tokens, mints
    exactly one uuid.uuid4() per distinct token, memoised so every
    reference to that token across the whole Change Plan resolves to the
    same id (the AI never sees or chooses a real id for a new entity --
    only OnyxJar, here, does -- and this minting is domain-agnostic, since
    a "new" token's string is opaque and never parsed). For "existing"
    refs, looks the key/key-path up against `dataset` for every domain
    except "relationship" (Relationship has no key or natural uniqueness
    constraint that could back a safe synthetic one, so it is addressed by
    its real id directly, unchanged from before this module supported keys
    at all).
    """

    def __init__(self, dataset):
        self._dataset = dataset
        self._minted: dict[str, uuid.UUID] = {}

    def resolve(self, ref: EntityRef, *, domain: str) -> uuid.UUID:
        if ref.kind == "new":
            if ref.id not in self._minted:
                self._minted[ref.id] = uuid.uuid4()
            return self._minted[ref.id]

        if domain == "relationship":
            return uuid.UUID(str(ref.id))

        entity = _KEY_LOOKUP[domain](self._dataset, ref.id)
        if entity is None:
            raise UnresolvableKeyError(domain=domain, key=ref.id)
        return uuid.UUID(str(entity.id))


def _parent_type_for(action: ChangeAction) -> str:
    if action.target_type in _MODEL_SCOPED_TARGET_TYPES:
        return "Model"
    if action.parent_ref is None:
        return ""
    if action.target_type == "AttributeDefinition":
        return action.parent_type or ""
    return _IMPLIED_PARENT_TYPE.get(action.target_type, "")


def _resolve_field_value(value, resolver: TempRefResolver, *, domain: str):
    """
    `value` is already a native Python value (FieldValue.native()) -- an
    EntityRef instance for a relationship endpoint/parent reference, or a
    plain scalar/dict otherwise. Type-driven, not key-driven: FieldValue
    itself is what now distinguishes an entity reference from a scalar.
    """
    if isinstance(value, EntityRef):
        return str(resolver.resolve(value, domain=domain))
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

    dataset = load_effective_dataset(model, proposal=None)
    resolver = TempRefResolver(dataset)
    specs: list[dict] = []
    action_ranges: list[tuple[ChangeAction, int, int]] = []
    claimed_keys: dict[tuple, set] = {}  # (target_type, parent_type, parent_id) -> keys claimed so far

    for action in change_plan.actions:
        target_id = resolver.resolve(action.target_ref, domain=target_domain(action.target_type))
        parent_type = _parent_type_for(action)
        if action.parent_ref is not None:
            parent_id = resolver.resolve(action.parent_ref, domain=parent_domain(action))
        elif parent_type == "Model":
            parent_id = model.id
        else:
            parent_id = None
        start = len(specs)
        field_domain = field_ref_domain(action.target_type)

        if action.operation == "create":
            after = {
                key: _resolve_field_value(value, resolver, domain=field_domain)
                for key, value in action.fields_dict().items()
            }
            bad = entity_fields.illegal_fields(action.target_type, after.keys(), operation="create")
            if bad:
                raise InvalidFieldError(target_type=action.target_type, target_id=target_id, field_names=bad)
            if keys.supports(action.target_type):
                _assign_key(model, proposal, action, parent_type, parent_id, after, claimed_keys)
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
            # Flat, one entry at a time -- NOT fields_dict(), which merges
            # "attributes.<key>" entries into a single nested dict for a
            # CREATE's one combined payload. An UPDATE's apply machinery
            # (model.services.proposal.submission._apply_attribute_update)
            # expects the literal dotted "attributes.<key>" string as its
            # own field-level change instead, exactly as entry.key already is.
            bad = entity_fields.illegal_fields(action.target_type, (entry.key for entry in action.fields), operation="update")
            if bad:
                raise InvalidFieldError(target_type=action.target_type, target_id=target_id, field_names=bad)

            for entry in action.fields:
                key = entry.key
                resolved_value = _resolve_field_value(entry.value.native(), resolver, domain=field_domain)
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
    One atomic attempt. If compile_change_plan raises a
    ChangePlanCompilationError (currently only InvalidFieldError -- an
    action supplied a `fields` key that isn't real for its target_type),
    that is caught here and converted into a
    CompileResult(issues=[...]) -- exactly the channel
    ai.services.orchestrator.run_ai_operation already treats as refinement
    feedback, so the AI gets a chance to retry with a corrected plan
    rather than the run failing outright. Any OTHER exception (e.g. an
    EvidenceService cap violation) is left to propagate: Django's atomic
    block rolls back everything written so far automatically, and this
    function does not need to special-case that; it is exactly the
    guarantee transaction.atomic() always gives.
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

        try:
            compile_change_plan(model=model, user=user, change_plan=change_plan, proposal=proposal)
        except ChangePlanCompilationError as failure:
            transaction.set_rollback(True)
            return CompileResult(proposal=None, issues=[failure.issue()])

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
