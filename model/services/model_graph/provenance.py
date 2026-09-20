"""
Provenance chain for a selected Object or Relationship.

Derived, not stored: there is no history subsystem. The chain is read from
the committed (COMPLETED) proposals whose changes targeted the record, with
each stored ProposalChange interpreted into a statement about what happened
to that record ("Renamed", "Set Owner", "Deactivated") rather than dumped as
raw operation/JSON. Evidence comes only from those changes' Evidence
References, so it is never attached to the record itself.

Entries are grouped by proposal (its change note, proposer and dates appear
once) and ordered oldest to newest by the model revision the proposal
produced, so the chain reads as the record's story. Nothing here exposes a
proposal id or URL: proposals are referred to by revision only.

Read-only; three queries however long the chain is.
"""

from __future__ import annotations

from model.models.proposal import Proposal, ProposalChange
from model.services.proposal.review import ProposalReviewService
from model.views.data_context import ATTRIBUTE_FIELD_PREFIX

from .details import display_value

Operation = ProposalChange.Operation

DEFAULT_LIMIT = 25

_OPERATION_ORDER = {
    Operation.CREATE: 0,
    Operation.UPDATE: 1,
    Operation.DELETE: 2,
}

# Shown when a relationship's endpoint object has since been deleted.
_MISSING_ENDPOINT = "an object that no longer exists"


def _iso(value):
    return value.isoformat() if value else None


def _field_label(field: str) -> str:
    return ProposalReviewService.FIELD_LABEL_OVERRIDES.get(field, field.replace("_", " ").title())


def _payload_value(payload: dict | None):
    """``(has_value, value)`` for a field-level change payload."""
    payload = payload or {}
    return "value" in payload, payload.get("value")


def _is_truthy(value) -> bool:
    return value is True or str(value).lower() == "true"


def _result(kind, summary, *, field=None, before=None, after=None, **extra) -> dict:
    return {
        "kind": kind,
        "summary": summary,
        "field": field,
        "before": before,
        "after": after,
        **extra,
    }


def _interpret_create(change, target_type, specs, endpoint_names, missing_endpoint=_MISSING_ENDPOINT) -> dict:
    after = change.after or {}
    inactive = "is_active" in after and not _is_truthy(after["is_active"])

    initial = []
    for key, value in (after.get("attributes") or {}).items():
        spec = specs.get(key) or {}
        shown = display_value(spec.get("dataType"), value)
        if shown is not None:
            initial.append({"label": spec.get("label") or key, "value": shown})

    if target_type == "Relationship":
        source = endpoint_names.get(str(after.get("subject_id")), missing_endpoint)
        target = endpoint_names.get(str(after.get("object_id")), missing_endpoint)
        return _result(
            "created",
            "Created relationship (inactive)" if inactive else "Created relationship",
            after=f"{source} → {target}",
            initial=initial,
            # Endpoint names are looked up now, not as they were at the time.
            currentNames=True,
        )

    return _result(
        "created",
        "Created (inactive)" if inactive else "Created",
        after=after.get("name") or None,
        initial=initial,
    )


def _interpret_update(change, specs) -> dict:
    payload = change.after or {}
    field = payload.get("field") or ""
    _, after_value = _payload_value(payload)
    has_before, before_value = _payload_value(change.before)

    if field.startswith(ATTRIBUTE_FIELD_PREFIX):
        key = field[len(ATTRIBUTE_FIELD_PREFIX):]
        spec = specs.get(key) or {}
        label = spec.get("label") or key
        data_type = spec.get("dataType")
        before = display_value(data_type, before_value)
        after = display_value(data_type, after_value)

        if after is None:
            kind, summary = "attribute_cleared", f"Cleared {label}"
        elif has_before and before is None:
            kind, summary = "attribute_set", f"Set {label}"
        else:
            kind, summary = "attribute_changed", f"Changed {label}"

        return _result(kind, summary, field=label, before=before, after=after)

    if field == "is_active":
        if _is_truthy(after_value):
            return _result("reactivated", "Reactivated")
        return _result("deactivated", "Deactivated")

    before = display_value(None, before_value)
    after = display_value(None, after_value)

    if field == "name":
        return _result("renamed", "Renamed", field="Name", before=before, after=after)

    if field == "description":
        return _result("described", "Changed description", field="Description", before=before, after=after)

    # Anything else stays legible rather than breaking the panel.
    label = _field_label(field) if field else "value"
    return _result("field_changed", f"Changed {label}", field=label, before=before, after=after)


def interpret_change(change, target_type, specs, endpoint_names=None, missing_endpoint=_MISSING_ENDPOINT) -> dict:
    """
    What one stored change did to its target, for a person.

    ``specs`` maps attribute key to ``{"label", "dataType"}``; an attribute
    whose definition no longer exists falls back to its key. ``endpoint_names``
    maps object ids to (current) names, used for Relationship CREATE;
    ``missing_endpoint`` is what an endpoint absent from that map is called.
    """
    if change.operation == Operation.CREATE:
        return _interpret_create(change, target_type, specs, endpoint_names or {}, missing_endpoint)
    if change.operation == Operation.DELETE:
        return _result("deleted", "Deleted")
    return _interpret_update(change, specs)


def _entry(proposal) -> dict:
    result = getattr(proposal, "submission_result", None)

    return {
        "revision": {
            "before": result.before_revision if result else None,
            "after": result.after_revision if result else None,
        },
        "title": proposal.title,
        "source": proposal.source,
        "proposer": proposal.created_by.email,
        "changeNote": proposal.summary,
        "submittedAt": _iso(proposal.submitted_at),
        "committedAt": _iso(proposal.completed_at or (result.updated_at if result else None)),
        "changes": [],
    }


_ID_CHUNK = 5000


def _provenance_for(changes, target_type, specs, endpoint_names, missing_endpoint, limit) -> dict:
    """The provenance chain built from one record's changes (already in order)."""
    entries: dict = {}
    for change in changes:
        entry = entries.get(change.proposal_id)
        if entry is None:
            entry = entries[change.proposal_id] = _entry(change.proposal)

        item = interpret_change(change, target_type, specs, endpoint_names, missing_endpoint)
        item["evidence"] = [
            {"source": e.source, "locator": e.locator, "note": e.note} for e in change.evidence.all()
        ]
        entry["changes"].append((_OPERATION_ORDER.get(change.operation, 1), item))

    ordered = list(entries.values())
    truncated = len(ordered) > limit
    ordered = ordered[-limit:] if truncated else ordered

    for entry in ordered:
        # Stable: CREATE first, then updates in the order they were made, DELETE last.
        entry["changes"] = [item for _, item in sorted(entry["changes"], key=lambda pair: pair[0])]

    return {"entries": ordered, "truncated": truncated}


def _completed_changes(model, target_type, target_ids):
    return (
        ProposalChange.objects.filter(
            proposal__model=model,
            proposal__status=Proposal.Status.COMPLETED,
            target_type=target_type,
            target_id__in=target_ids,
        )
        .select_related("proposal__created_by", "proposal__submission_result")
        .prefetch_related("evidence")
        .order_by("proposal__submission_result__after_revision", "created_at", "id")
    )


def build_provenance(model, target_type, target_id, specs=None, limit=DEFAULT_LIMIT) -> dict:
    """
    The provenance chain of one Object or Relationship of ``model``.

    ``specs``: attribute key -> ``{"label", "dataType"}`` (see
    ``interpret_change``). When more than ``limit`` proposals touched the
    record, the most recent ``limit`` are kept and ``truncated`` is set; they
    are still returned oldest first.
    """
    specs = specs or {}

    changes = list(_completed_changes(model, target_type, [target_id]))

    endpoint_names = {}
    if target_type == "Relationship":
        endpoint_names = ProposalReviewService.resolve_object_names(
            changes, ProposalReviewService.build_create_lookup(changes)
        )

    return _provenance_for(changes, target_type, specs, endpoint_names, _MISSING_ENDPOINT, limit)


def build_provenance_bulk(
    model,
    target_type,
    target_ids,
    specs_for,
    *,
    endpoint_names,
    missing_endpoint=_MISSING_ENDPOINT,
    limit=DEFAULT_LIMIT,
) -> dict:
    """
    Provenance chains for many records of one type, keyed by (string) record id.

    Equivalent to calling ``build_provenance`` per id but in a handful of
    queries however many records there are. Every requested id has an entry
    (empty when no committed proposal touched it).

    ``specs_for(record_id)`` gives that record's attribute specs. Unlike the
    single-record builder, ``endpoint_names`` is supplied by the caller (object
    id -> name) so it can decide which names may be disclosed; an endpoint not
    in the map is called ``missing_endpoint``.
    """
    ids = [str(target_id) for target_id in target_ids]
    by_target: dict[str, list] = {target_id: [] for target_id in ids}

    for start in range(0, len(ids), _ID_CHUNK):
        for change in _completed_changes(model, target_type, ids[start : start + _ID_CHUNK]):
            by_target[str(change.target_id)].append(change)

    return {
        target_id: _provenance_for(
            changes, target_type, specs_for(target_id) or {}, endpoint_names, missing_endpoint, limit
        )
        for target_id, changes in by_target.items()
    }
