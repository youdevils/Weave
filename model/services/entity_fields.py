"""
The legal `fields`/attribute keys for a CREATE or UPDATE ProposalChange,
per target_type -- a deliberately hand-maintained allowlist, narrower than
"every real Django field" on each model, for the same reason
model.services.proposal.submission.MODEL_EDITABLE_FIELDS is hand-maintained
rather than introspected: a Proposal must never reach a field through bare
hasattr()/kwarg permissiveness that was never meant to be externally
settable (id, created_at/updated_at, and any future internal-only field).

Single source of truth for what were previously independent, and in one
case verbatim duplicated, allowlists spread across
model/views/object_type_editor.py, model/views/relationship_type_editor.py
and model/views/data_object_editor.py -- those views now import from here.
ai.services.proposal_compiler's AI-generated-field preflight check (see
InvalidFieldError there) reuses this directly, rather than maintaining a
fourth copy.
"""

from model.services.field_paths import ATTRIBUTE_FIELD_PREFIX

OBJECT_TYPE_PROPERTY_FIELDS = frozenset({"name", "key", "description", "sort_order"})
OBJECT_TYPE_LIFECYCLE_FIELD = "is_active"

RELATIONSHIP_TYPE_PROPERTY_FIELDS = frozenset({"name", "key", "description", "sort_order"})
RELATIONSHIP_TYPE_LIFECYCLE_FIELD = "is_active"

ATTRIBUTE_PROPERTY_FIELDS = frozenset({
    "name", "key", "data_type", "description",
    "required", "nullable", "default_value", "sort_order", "config",
})
ATTRIBUTE_LIFECYCLE_FIELD = "is_active"

RELATIONSHIP_TYPE_RULE_FIELDS = frozenset({
    "subject_type_id", "object_type_id",
    "subject_minimum", "subject_maximum",
    "object_minimum", "object_maximum",
})

OBJECT_PROPERTY_FIELDS = frozenset({"name", "description"})
OBJECT_LIFECYCLE_FIELD = "is_active"

# No equivalent constant existed anywhere for Relationship before this --
# its field-level edits only ever went through the generic
# hasattr()/validate_relationship_field path, with no editor-view
# allowlist of its own.
RELATIONSHIP_PROPERTY_FIELDS = frozenset({"valid_from", "valid_to"})
RELATIONSHIP_LIFECYCLE_FIELD = "is_active"
RELATIONSHIP_ENDPOINT_FIELDS = ("subject_id", "object_id")  # mirrors ai.services.change_plan's own constant

_ATTRIBUTE_BEARING_FIELD = "attributes"
_ATTRIBUTE_HOST_TYPES = ("Object", "Relationship")

_LEGAL_FIELDS = {
    "ObjectType": OBJECT_TYPE_PROPERTY_FIELDS | {OBJECT_TYPE_LIFECYCLE_FIELD},
    "RelationshipType": RELATIONSHIP_TYPE_PROPERTY_FIELDS | {RELATIONSHIP_TYPE_LIFECYCLE_FIELD},
    "AttributeDefinition": ATTRIBUTE_PROPERTY_FIELDS | {ATTRIBUTE_LIFECYCLE_FIELD},
    "RelationshipTypeRule": RELATIONSHIP_TYPE_RULE_FIELDS,
    "Object": OBJECT_PROPERTY_FIELDS | {OBJECT_LIFECYCLE_FIELD, _ATTRIBUTE_BEARING_FIELD},
    "Relationship": (
        RELATIONSHIP_PROPERTY_FIELDS
        | {RELATIONSHIP_LIFECYCLE_FIELD, _ATTRIBUTE_BEARING_FIELD}
        | set(RELATIONSHIP_ENDPOINT_FIELDS)
    ),
}


def illegal_fields(target_type: str, field_keys) -> list[str]:
    """
    Which of `field_keys` are not legal for `target_type`, preserving
    input order. For Object/Relationship, a key beginning with
    "attributes." (the per-instance dynamic-attribute addressing
    model.services.field_paths already defines, used by UPDATE's
    one-field-at-a-time specs) is always legal regardless of which
    specific attribute it names -- whether THAT attribute actually exists
    is a separate, value-level check already performed elsewhere
    (model.services.validation.attributes), not a key-legality concern
    this function owns.
    """

    legal = _LEGAL_FIELDS.get(target_type)
    if legal is None:
        return list(field_keys)  # unknown target_type: nothing is legal

    illegal = []
    for key in field_keys:
        if key in legal:
            continue
        if target_type in _ATTRIBUTE_HOST_TYPES and key.startswith(ATTRIBUTE_FIELD_PREFIX):
            continue
        illegal.append(key)
    return illegal
