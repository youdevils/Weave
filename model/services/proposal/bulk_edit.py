"""
Bulk-edit orchestration for data Objects.

This module is deliberately thin: it never writes canonical data or
ProposalChange rows through any mechanism other than the exact calls
data_object_editor.py already makes for a single field on a single object
(ProposalService.record_change / discard_change, coerce_attribute_value,
validate_attribute_value / validate_object_field). Bulk edit is an
alternative interaction surface over those primitives, not an alternative
business rule.

Two calling conventions matter and must not be confused:

  * `collect_effective_state` is DISPLAY-ONLY. It uses
    model.views.data_context.object_effective_values, which overlays a
    user's own pending proposal changes on top of canonical state -- the
    right thing to show as "current value" / "Mixed values" in the editor.

  * `apply_edits` (and the validation it re-runs before writing) always
    compares against an object's TRUE CANONICAL value, never the effective
    one. ProposalService.record_change unconditionally overwrites an
    existing change's `before` on every upsert call. The single-field
    editor gets away with calling it repeatedly only because it always
    recomputes `before` from canonical state, which never moves within a
    working proposal's lifetime. Using the effective value instead would
    silently launder a change's true original baseline through whatever
    was previously proposed, the first time the same field is bulk-edited
    twice.
"""

import hashlib
import json
import uuid as uuid_module
from dataclasses import dataclass, field as dc_field
from types import SimpleNamespace

from django.db import transaction
from django.db.models import Count, Max

from model.models.object import Object
from model.models.proposal import ProposalChange
from model.services.coercion import coerce_attribute_value
from model.services.field_paths import ATTRIBUTE_FIELD_PREFIX, attribute_field_name
from model.services.proposal.proposal import ProposalService
from model.services.validation.attributes import validate_attribute_value
from model.views.data_context import object_create_change, object_effective_values

MODE_NO_CHANGE = "nochange"
MODE_SET = "set"
MODE_CLEAR = "clear"
MODE_ACTIVATE = "activate"
MODE_RETIRE = "retire"

LIFECYCLE_FIELD = "is_active"

# 4 x data_objects.PAGE_SIZE (25): generously covers any legitimate
# "select all visible" use on the current index page size, while still
# bounding a hand-crafted request. Chosen rather than an unbounded value;
# never silently truncated -- a selection over this is rejected outright.
MAX_BULK_SELECTION = 100


class BulkEditError(Exception):
    """Base for the selection-shape errors the view turns into a 400."""


class EmptySelectionError(BulkEditError):
    pass


class TooManySelectedError(BulkEditError):
    def __init__(self, count):
        self.count = count
        super().__init__(f"Select at most {MAX_BULK_SELECTION} records at a time.")


class UnresolvedSelectionError(BulkEditError):
    """
    Raised when any submitted id fails to resolve to a record scoped to
    this model+object_type. The whole request is rejected -- nothing is
    silently dropped and continued around.
    """

    def __init__(self, missing_count, total_count):
        self.missing_count = missing_count
        self.total_count = total_count
        super().__init__(
            f"{missing_count} of {total_count} selected records could not "
            "be found. Please refresh and try again."
        )


class BulkEditValidationError(BulkEditError):
    def __init__(self, errors):
        self.errors = errors
        super().__init__("One or more fields are invalid.")


@dataclass(frozen=True)
class FieldEdit:
    field: str  # "is_active" or "attributes.<key>"
    mode: str  # MODE_NO_CHANGE / MODE_SET / MODE_CLEAR / MODE_ACTIVATE / MODE_RETIRE
    raw_value: str = ""


@dataclass
class ObjectFailure:
    object_id: str
    object_name: str
    field_errors: dict


@dataclass
class BulkEditResult:
    ok: bool
    failures: list = dc_field(default_factory=list)


# =====================================================================
# Input bounding
# =====================================================================


def dedupe_and_bound(raw_ids):
    """
    Deduplicate while preserving first-seen order, then enforce the
    selection-size bounds. Raises EmptySelectionError / TooManySelectedError
    rather than silently truncating.
    """

    ids = list(dict.fromkeys(str(value) for value in raw_ids if str(value).strip()))

    if not ids:
        raise EmptySelectionError("Select at least one record.")

    if len(ids) > MAX_BULK_SELECTION:
        raise TooManySelectedError(len(ids))

    return ids


# =====================================================================
# ID resolution -- strict, all-or-nothing
# =====================================================================


def _is_uuid(value):
    try:
        uuid_module.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return False
    return True


def resolve_working_objects(model, object_type, proposal, object_ids):
    """
    Every id must resolve to a canonical Object or a proposal-only CREATE
    change scoped to this model+object_type, or the whole selection is
    rejected (UnresolvedSelectionError) -- never trust a browser-supplied
    id beyond using it to filter a queryset scoped to model+object_type,
    and never apply a partial set when some ids don't resolve.

    Returns a list of (obj, proposal_only) pairs, in the same order as
    `object_ids`.
    """

    well_formed = {value for value in object_ids if _is_uuid(value)}

    canonical = {
        str(obj.id): obj
        for obj in Object.objects.filter(
            id__in=well_formed,
            model=model,
            object_type_id=object_type.id,
        )
    }

    resolved = []
    missing = 0

    for object_id in object_ids:

        obj = canonical.get(object_id)

        if obj is not None:
            resolved.append((obj, False))
            continue

        if object_id in well_formed:

            create_change = object_create_change(object_id, proposal)

            if create_change is not None and str(create_change.parent_id) == str(object_type.id):

                after = create_change.after or {}

                proposed = SimpleNamespace(
                    id=create_change.target_id,
                    model_id=model.id,
                    object_type_id=object_type.id,
                    name=after.get("name", ""),
                    description=after.get("description", ""),
                    is_active=after.get("is_active", True),
                    attributes=dict(after.get("attributes") or {}),
                )

                resolved.append((proposed, True))
                continue

        missing += 1

    if missing:
        raise UnresolvedSelectionError(missing, len(object_ids))

    return resolved


# =====================================================================
# Display -- Mixed values
# =====================================================================


def collect_effective_state(objects, attribute_definitions, proposal):
    """
    DISPLAY ONLY -- see the module docstring. {field: {"value", "is_mixed"}}
    across the given objects, reflecting each object's own pending edits.
    Never consulted by apply_edits' write path.
    """

    fields = [attribute_field_name(definition.key) for definition in attribute_definitions]
    fields.append(LIFECYCLE_FIELD)

    values_by_field = {field: [] for field in fields}

    for obj, proposal_only in objects:

        if proposal_only:
            effective = {
                "is_active": obj.is_active,
                "attributes": dict(obj.attributes or {}),
            }
        else:
            effective = object_effective_values(obj, proposal)

        for definition in attribute_definitions:
            values_by_field[attribute_field_name(definition.key)].append(
                effective["attributes"].get(definition.key)
            )

        values_by_field[LIFECYCLE_FIELD].append(effective["is_active"])

    result = {}

    for field, values in values_by_field.items():
        distinct = set(values)
        is_mixed = len(distinct) > 1
        result[field] = {
            "value": values[0] if (values and not is_mixed) else None,
            "is_mixed": is_mixed,
        }

    return result


# =====================================================================
# Coerce + validate -- pure, shared by preview and apply
# =====================================================================


def _coerce_and_validate_edits(edits, attribute_definitions):
    """
    Pure, no writes. Returns (coerced: {field: value}, errors: {field:
    message}) for every edit whose mode isn't "No change". Shared by
    validate_edits (preview) and apply_edits, which always re-runs this
    rather than trusting a stale preview.
    """

    definitions_by_field = {
        attribute_field_name(definition.key): definition for definition in attribute_definitions
    }

    coerced = {}
    errors = {}

    for edit in edits:

        if edit.field == LIFECYCLE_FIELD:

            if edit.mode == MODE_NO_CHANGE:
                continue

            if edit.mode not in (MODE_ACTIVATE, MODE_RETIRE):
                errors[edit.field] = "Status must be Activate or Retire."
                continue

            coerced[edit.field] = edit.mode == MODE_ACTIVATE
            continue

        definition = definitions_by_field.get(edit.field)

        if definition is None:
            errors[edit.field] = "Unknown attribute."
            continue

        if edit.mode == MODE_NO_CHANGE:
            continue

        if edit.mode == MODE_CLEAR:

            issue = validate_attribute_value(definition, None, field=edit.field)

            if issue is not None:
                errors[edit.field] = issue.message
            else:
                coerced[edit.field] = None

            continue

        if edit.mode != MODE_SET:
            errors[edit.field] = "Invalid mode."
            continue

        try:
            value = coerce_attribute_value(definition.data_type, edit.raw_value)
        except ValueError as exc:
            errors[edit.field] = str(exc)
            continue

        issue = validate_attribute_value(definition, value, field=edit.field)

        if issue is not None:
            errors[edit.field] = issue.message
            continue

        coerced[edit.field] = value

    return coerced, errors


def validate_edits(objects, edits, attribute_definitions):
    """
    Pure, no writes. Every validation failure found by
    _coerce_and_validate_edits is attributed to every selected object,
    since v1's field set (plain attributes + is_active) has no
    cross-object dependency -- a field's validity never depends on which
    object it's applied to. The per-object shape is kept anyway so a
    future cross-object rule doesn't require restructuring this report.
    """

    _, errors = _coerce_and_validate_edits(edits, attribute_definitions)

    failures = []

    if errors:
        for obj, proposal_only in objects:
            failures.append(
                ObjectFailure(
                    object_id=str(obj.id),
                    object_name=obj.name,
                    field_errors=dict(errors),
                )
            )

    return BulkEditResult(ok=not failures, failures=failures)


# =====================================================================
# Apply -- the only place anything is written
# =====================================================================


@transaction.atomic
def apply_edits(proposal, object_type, objects, edits, attribute_definitions):
    """
    Re-validates (never trusts a stale preview) then commits every
    (object, field) pair whose mode isn't "No change", all inside one
    transaction. Raises BulkEditValidationError, writing nothing, if
    re-validation fails.
    """

    coerced, errors = _coerce_and_validate_edits(edits, attribute_definitions)

    if errors:
        raise BulkEditValidationError(errors)

    if not coerced:
        return

    for obj, proposal_only in objects:
        _apply_to_one(proposal, object_type, obj, proposal_only, coerced)


def _apply_to_one(proposal, object_type, obj, proposal_only, coerced):

    if proposal_only:

        create_change = object_create_change(obj.id, proposal)
        after = dict(create_change.after or {})
        attributes = dict(after.get("attributes") or {})

        for field, value in coerced.items():

            if field.startswith(ATTRIBUTE_FIELD_PREFIX):
                attributes[field[len(ATTRIBUTE_FIELD_PREFIX):]] = value
            else:
                after[field] = value

        after["attributes"] = attributes
        create_change.after = after
        create_change.save(update_fields=["after", "updated_at"])
        ProposalService.reset_validation(proposal)
        return

    for field, value in coerced.items():

        if field.startswith(ATTRIBUTE_FIELD_PREFIX):
            key = field[len(ATTRIBUTE_FIELD_PREFIX):]
            canonical_value = (obj.attributes or {}).get(key)
        else:
            canonical_value = getattr(obj, field)

        if value == canonical_value:

            ProposalService.discard_change(
                proposal=proposal,
                target_type="Object",
                target_id=obj.id,
                field=field,
            )
            continue

        ProposalService.record_change(
            proposal=proposal,
            operation=ProposalChange.Operation.UPDATE,
            target_type="Object",
            target_id=obj.id,
            parent_type="ObjectType",
            parent_id=object_type.id,
            field=field,
            before={"field": field, "value": canonical_value},
            after={"field": field, "value": value},
        )


# =====================================================================
# Preview <-> Apply fingerprint
# =====================================================================


def proposal_state_signature(proposal):
    """
    A cheap, derived "has this proposal changed" signal, computed from
    existing data rather than a new field. Proposal.updated_at alone is
    not reliable for this: ProposalService.reset_validation only saves
    (and so only bumps updated_at) when validation_status is transitioning
    away from NOT_VALIDATED, which is a no-op once a proposal is already
    NOT_VALIDATED -- the normal steady state while a user is mid-edit. So
    instead this aggregates the proposal's own (FK-scoped, small) change
    set: its count and the latest change's updated_at.
    """

    if proposal is None:
        return None

    aggregate = proposal.changes.aggregate(count=Count("id"), latest=Max("updated_at"))

    latest = aggregate["latest"]

    return (str(proposal.id), aggregate["count"], latest.isoformat() if latest else None)


def compute_fingerprint(*, model_id, object_type_id, object_ids, edits, proposal):
    """
    Ties an Apply request to the exact operation a Preview showed the
    user: same model + type + selected records + edits + proposal state.
    Defense in depth only -- apply_edits always re-validates against
    current state regardless of this check's outcome.
    """

    payload = {
        "model_id": str(model_id),
        "object_type_id": str(object_type_id),
        "object_ids": sorted(str(value) for value in object_ids),
        "edits": sorted((edit.field, edit.mode, edit.raw_value) for edit in edits),
        "proposal_state": list(proposal_state_signature(proposal) or ()),
    }

    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
