"""
Deriving a unique, model-scoped `key` (ObjectType.key / RelationshipType.key)
from a human-entered display name.

Today, `key` is always supplied explicitly -- typed by a user in the manual
editors (model/views/object_type_editor.py, relationship_type_editor.py) or
written literally in a model_template definition. This module exists for the
one case neither of those covers: an AI-generated CREATE action that left
`key` blank, which must never reach the database that way (see
ai.services.proposal_compiler._apply_key_fallback, its only caller today).

It is also the seam a later, broader refactor (where no caller -- human or
AI -- supplies a key at all, and OnyxJar always derives one) can build on
without duplicating key-generation rules in multiple subsystems. Deliberately
three small, composable functions rather than one; no import from `ai` or
`assisted`.
"""

from __future__ import annotations

from django.utils.text import slugify

from model.models.object_type import ObjectType
from model.models.relationship_type import RelationshipType

MAX_KEY_LENGTH = 100  # matches SlugField(max_length=100) on every key-bearing model today

# Explicit and small on purpose -- easy to extend later (e.g. AttributeDefinition,
# once it gets its own (parent, key) uniqueness constraint -- not added now).
_KEY_MODELS = {
    "ObjectType": ObjectType,
    "RelationshipType": RelationshipType,
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


def make_unique_key(name: str, used_keys) -> str | None:
    """
    A key derived from `name`, guaranteed not to collide with any of
    `used_keys`. Returns None if `name` has no sluggable characters at all
    -- deliberately NOT a silent placeholder fallback (unlike the existing
    `slugify(...) or "model"` filename helpers in ingestion/publication):
    the caller is expected to turn None into a deterministic validation
    issue instead of creating a confusingly-named real entity.

    Collisions resolve deterministically (base, base_2, base_3, ...), never
    randomly, respecting SlugField(max_length=100) even after a suffix is
    appended.
    """

    base = slugify_key(name)[:MAX_KEY_LENGTH]
    if not base:
        return None

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


def existing_keys_for(target_type: str, model) -> set[str]:
    """
    Every key already in use for `target_type` within `model`'s canonical
    state -- a direct query, mirroring model.services.proposal.submission's
    own _duplicate_key_issue approach (not EffectiveDataset). A caller
    creating more than one new entity in a single batch must union this
    with keys it has itself already claimed earlier in that same batch --
    this function only reflects the DB, by design.
    """

    model_cls = _KEY_MODELS[target_type]
    return set(model_cls.objects.filter(model=model).values_list("key", flat=True))
