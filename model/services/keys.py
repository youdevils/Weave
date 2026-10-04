"""
Deriving a unique `key` (ObjectType.key / RelationshipType.key /
AttributeDefinition.key / Object.key) from a human-entered display name.

The application generates and maintains every key: no caller -- human
editor, AI-generated Change Plan, or import -- ever supplies one. This
module is the single place that rule lives; nothing else should
duplicate it (see generate_key, the one entry point every caller uses).

Deliberately small, composable functions; no import from `ai` or
`assisted`, and no module-level import of anything under
`model.models.proposal` / `model.services.proposal` -- `ingestion`'s
architecture test (test_the_planners_do_not_read_proposals) forbids its
planner modules from reading proposal state, and this module must stay
safe to import from there.
"""

from __future__ import annotations

from django.utils.text import slugify

from model.models.attribute_definition import AttributeDefinition
from model.models.object import Object
from model.models.object_type import ObjectType
from model.models.relationship_type import RelationshipType

MAX_KEY_LENGTH = 100  # matches SlugField(max_length=100) on every key-bearing model

# A per-type base word used when a name has no sluggable characters at all
# (e.g. it's written only in a script slugify() can't fold to ASCII).
# Creation must never block just because of the name's alphabet.
_FALLBACK_BASE = {
    "ObjectType": "object_type",
    "RelationshipType": "relationship_type",
    "AttributeDefinition": "attribute",
    "Object": "object",
}

_KEY_MODELS = {
    "ObjectType": ObjectType,
    "RelationshipType": RelationshipType,
    "AttributeDefinition": AttributeDefinition,
    "Object": Object,
}

# Key-bearing types scoped by something other than "model" alone (the
# straightforward FK every other key-bearing model uses).
# AttributeDefinition is scoped to its owning ObjectType or
# RelationshipType only (it has no `model` FK of its own). Object is
# scoped to BOTH its model and its owning ObjectType (the same name can
# recur under a different type or a different model).
_ATTRIBUTE_PARENT_FIELD = {
    "ObjectType": "object_type_id",
    "RelationshipType": "relationship_type_id",
}


def supports(target_type: str) -> bool:
    return target_type in _KEY_MODELS


def slugify_key(name: str) -> str:
    """
    name -> underscore-style slug, matching this codebase's existing hand-
    written key convention (business_process, go_live, depends_on -- every
    key in this codebase uses underscores; Django's own slugify() alone
    produces hyphens). Built on slugify()'s unicode-folding/charset-stripping
    rather than reimplementing it.
    """

    return slugify(name or "").replace("-", "_")


def is_valid_key(value) -> bool:
    """Whether `value` could itself have come out of slugify_key/make_unique_key."""

    if not isinstance(value, str) or not value:
        return False
    if len(value) > MAX_KEY_LENGTH:
        return False
    return slugify_key(value) == value


def make_unique_key(name: str, used_keys, *, fallback: str | None = None) -> str | None:
    """
    A key derived from `name`, guaranteed not to collide with any of
    `used_keys`. If `name` has no sluggable characters at all, falls back
    to `fallback` (suffixed the same way) when given, else returns None.

    Collisions resolve deterministically (base, base_2, base_3, ...), never
    randomly, respecting SlugField(max_length=100) even after a suffix is
    appended.
    """

    base = slugify_key(name)[:MAX_KEY_LENGTH]
    if not base:
        if not fallback:
            return None
        base = fallback[:MAX_KEY_LENGTH]

    used = set(used_keys)
    if base not in used:
        return base

    suffix = 2
    while True:
        tail = f"_{suffix}"
        candidate = base[: MAX_KEY_LENGTH - len(tail)] + tail
        if candidate not in used:
            return candidate
        suffix += 1


def existing_keys_for(target_type: str, model, *, parent_type: str | None = None, parent_id=None) -> set[str]:
    """
    Every key already in use for `target_type` within its canonical scope
    -- a direct query, mirroring model.services.proposal.submission's own
    _duplicate_key_issue approach (not EffectiveDataset). A caller creating
    more than one new entity in a single batch must union this with keys it
    has itself already claimed earlier in that same batch -- this function
    only reflects the DB, by design.

    ObjectType/RelationshipType are scoped by `model`. AttributeDefinition
    is scoped by its owning ObjectType or RelationshipType -- pass
    `parent_type`/`parent_id` (the parent's id) for it. Object is scoped
    by `model` AND its owning ObjectType -- pass `parent_id` (the
    ObjectType's id) for it.
    """

    model_cls = _KEY_MODELS[target_type]

    if target_type == "AttributeDefinition":
        field = _ATTRIBUTE_PARENT_FIELD.get(parent_type)
        if field is None or parent_id is None:
            return set()
        return set(model_cls.objects.filter(**{field: parent_id}).values_list("key", flat=True))

    if target_type == "Object":
        if parent_id is None:
            return set()
        return set(
            model_cls.objects.filter(model=model, object_type_id=parent_id).values_list("key", flat=True)
        )

    return set(model_cls.objects.filter(model=model).values_list("key", flat=True))


def claimed_keys_in_proposal(proposal, target_type: str, *, parent_type: str | None = None, parent_id=None) -> set[str]:
    """
    Keys already claimed by other CREATE changes of `target_type` (with
    the same parent, for AttributeDefinition/Object) within `proposal` --
    a database-only read (existing_keys_for) has no visibility into
    sibling in-progress changes in the same working proposal. Generalises
    what the editors' own per-request `claimed` sets used to track one
    request at a time.

    Proposal-model types are only ever used from inside a live request/
    submission, never from ingestion's planners, so the import stays
    lazy and local to this function rather than a module-level import.
    """

    from model.models.proposal import ProposalChange

    if proposal is None:
        return set()

    changes = proposal.changes.filter(
        target_type=target_type,
        operation=ProposalChange.Operation.CREATE,
    )

    if target_type in ("AttributeDefinition", "Object"):
        changes = changes.filter(parent_type=parent_type, parent_id=parent_id)

    claimed = set()
    for change in changes:
        after = change.after or {}
        key = after.get("key")
        if isinstance(key, str) and key:
            claimed.add(key)
    return claimed


def generate_key(
    target_type: str,
    name: str,
    *,
    model,
    proposal=None,
    parent_type: str | None = None,
    parent_id=None,
    also_used=(),
) -> str:
    """
    The one entry point every caller (human editors, the AI compiler,
    import, model-template instantiation) uses to assign a key. Unions
    canonical keys, keys already claimed by other CREATEs in the same
    working `proposal`, and any further `also_used` keys the caller is
    tracking itself (e.g. allocating several new keys in one pass before
    any of them is actually recorded), then derives a unique key from
    `name` via make_unique_key, falling back to a per-type base word if
    `name` has no sluggable characters at all.
    """

    used = (
        existing_keys_for(target_type, model, parent_type=parent_type, parent_id=parent_id)
        | claimed_keys_in_proposal(proposal, target_type, parent_type=parent_type, parent_id=parent_id)
        | set(also_used)
    )

    return make_unique_key(name, used, fallback=_FALLBACK_BASE.get(target_type, target_type.lower()))
