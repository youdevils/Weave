import json
import uuid
from types import SimpleNamespace

from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render

from model.models.attribute_definition import AttributeDefinition
from model.models.relationship_type import RelationshipType
from model.models.relationship_type_rule import RelationshipTypeRule
from model.models.proposal import ProposalChange
from model.services.proposal.proposal import ProposalService
from model.views.common_context import get_model_context

# =====================================================================
# Field definitions
# =====================================================================

RELATIONSHIP_TYPE_PROPERTY_FIELDS = {
    "name",
    "key",
    "description",
    "sort_order",
}

RELATIONSHIP_TYPE_LIFECYCLE_FIELD = "is_active"

ATTRIBUTE_PROPERTY_FIELDS = {
    "name",
    "key",
    "data_type",
    "description",
    "required",
    "nullable",
    "default_value",
    "sort_order",
    "config",
}

ATTRIBUTE_LIFECYCLE_FIELD = "is_active"

RULE_FIELDS = {
    "subject_type_id",
    "object_type_id",
    "subject_minimum",
    "subject_maximum",
    "subject_required",
    "object_minimum",
    "object_maximum",
    "object_required",
}


# =====================================================================
# Generic helpers
# =====================================================================


def _serialize_value(value):
    if isinstance(value, bool):
        return "true" if value else "false"

    if isinstance(value, (dict, list)):
        return json.dumps(value)

    if value is None:
        return ""

    return str(value)


def _coerce_boolean(value, label):
    value = str(value).strip().lower()

    if value in {"true", "1", "yes", "on"}:
        return True

    if value in {"false", "0", "no", "off"}:
        return False

    raise ValueError(f"{label} must be true or false.")


def _working_proposal(model, user):
    return ProposalService.get_or_create_working(
        model=model,
        user=user,
    )


# =====================================================================
# RelationshipType helpers
# =====================================================================


def _relationship_type_create_change(
    relationship_type_id,
    proposal,
):
    if not proposal:
        return None

    return (
        proposal.changes.filter(
            target_type="RelationshipType",
            target_id=relationship_type_id,
            operation=ProposalChange.Operation.CREATE,
        )
        .order_by("created_at")
        .first()
    )


def _relationship_type_proposed_fields(
    relationship_type_id,
    proposal,
):
    result = {
        field: False
        for field in (
            *RELATIONSHIP_TYPE_PROPERTY_FIELDS,
            RELATIONSHIP_TYPE_LIFECYCLE_FIELD,
        )
    }

    if not proposal:
        return result

    create_change = _relationship_type_create_change(
        relationship_type_id,
        proposal,
    )

    if create_change:
        for field in result:
            result[field] = True

    for change in proposal.changes.filter(
        target_type="RelationshipType",
        target_id=relationship_type_id,
        operation=ProposalChange.Operation.UPDATE,
    ):
        after = change.after or {}
        field = after.get("field")

        if field in result:
            result[field] = True

    return result


def _relationship_type_proposed_only(
    relationship_type_id,
    proposal,
):
    create_change = _relationship_type_create_change(
        relationship_type_id,
        proposal,
    )

    if create_change is None:
        return None

    values = dict(
        create_change.after or {},
    )

    for change in proposal.changes.filter(
        target_type="RelationshipType",
        target_id=relationship_type_id,
        operation=ProposalChange.Operation.UPDATE,
    ).order_by("created_at"):

        after = change.after or {}
        field = after.get("field")

        if (
            field
            in RELATIONSHIP_TYPE_PROPERTY_FIELDS
            | {
                RELATIONSHIP_TYPE_LIFECYCLE_FIELD,
            }
            and "value" in after
        ):

            values[field] = after["value"]

    return SimpleNamespace(
        id=relationship_type_id,
        model_id=create_change.parent_id,
        name=values.get("name", ""),
        key=values.get("key", ""),
        description=values.get("description", ""),
        sort_order=values.get("sort_order", 0),
        is_active=values.get("is_active", True),
    )


# =====================================================================
# Attribute helpers
# =====================================================================


def _attribute_canonical_values(attribute):
    return {
        "name": attribute.name,
        "key": attribute.key,
        "data_type": attribute.data_type,
        "description": attribute.description,
        "required": attribute.required,
        "nullable": attribute.nullable,
        "default_value": attribute.default_value,
        "sort_order": attribute.sort_order,
        "config": attribute.config or {},
        "is_active": attribute.is_active,
    }


def _attribute_create_change(
    attribute_id,
    proposal,
):
    if not proposal:
        return None

    return (
        proposal.changes.filter(
            target_type="AttributeDefinition",
            target_id=attribute_id,
            operation=ProposalChange.Operation.CREATE,
        )
        .order_by("created_at")
        .first()
    )


def _attribute_update_changes(
    attribute_id,
    proposal,
):
    if not proposal:
        return []

    return list(
        proposal.changes.filter(
            target_type="AttributeDefinition",
            target_id=attribute_id,
            operation=ProposalChange.Operation.UPDATE,
        ).order_by("created_at")
    )


def _attribute_effective_values(
    attribute,
    proposal,
):
    values = _attribute_canonical_values(
        attribute,
    )

    for change in _attribute_update_changes(
        attribute.id,
        proposal,
    ):
        after = change.after or {}
        field = after.get("field")

        if field in values and "value" in after:
            values[field] = after["value"]

    return values


def _attribute_proposal_values(
    attribute_id,
    relationship_type,
    proposal,
):
    attribute = None

    if isinstance(
        relationship_type,
        RelationshipType,
    ):
        attribute = AttributeDefinition.objects.filter(
            id=attribute_id,
            relationship_type=relationship_type,
        ).first()

    if attribute:
        return (
            attribute,
            _attribute_effective_values(
                attribute,
                proposal,
            ),
            False,
        )

    create_change = _attribute_create_change(
        attribute_id,
        proposal,
    )

    if create_change is None:
        return None, None, False

    values = dict(
        create_change.after or {},
    )

    for change in _attribute_update_changes(
        attribute_id,
        proposal,
    ):
        after = change.after or {}
        field = after.get("field")

        if (
            field
            in ATTRIBUTE_PROPERTY_FIELDS
            | {
                ATTRIBUTE_LIFECYCLE_FIELD,
            }
            and "value" in after
        ):

            values[field] = after["value"]

    return (
        None,
        {
            "name": values.get("name", ""),
            "key": values.get("key", ""),
            "data_type": values.get(
                "data_type",
                AttributeDefinition.DataType.TEXT,
            ),
            "description": values.get("description", ""),
            "required": values.get("required", False),
            "nullable": values.get("nullable", False),
            "default_value": values.get("default_value"),
            "sort_order": values.get("sort_order", 0),
            "config": values.get("config") or {},
            "is_active": values.get("is_active", True),
        },
        True,
    )


def _attribute_proposed_fields(
    attribute_id,
    proposal,
):
    result = {
        field: False
        for field in (
            *ATTRIBUTE_PROPERTY_FIELDS,
            ATTRIBUTE_LIFECYCLE_FIELD,
        )
    }

    if not proposal:
        return result

    for change in proposal.changes.filter(
        target_type="AttributeDefinition",
        target_id=attribute_id,
    ).order_by("created_at"):

        if change.operation == ProposalChange.Operation.CREATE:
            for field in result:
                result[field] = True

            continue

        after = change.after or {}
        field = after.get("field")

        if field in result:
            result[field] = True

    return result


def _attribute_is_proposed(
    attribute_id,
    proposal,
):
    if not proposal:
        return False

    return proposal.changes.filter(
        target_type="AttributeDefinition",
        target_id=attribute_id,
    ).exists()


def _build_attribute_view_objects(
    relationship_type,
    proposal,
):
    attributes = []
    canonical_attributes = []

    if isinstance(
        relationship_type,
        RelationshipType,
    ):
        canonical_attributes = list(
            AttributeDefinition.objects.filter(
                relationship_type=relationship_type,
            ).order_by(
                "sort_order",
                "name",
            )
        )

    canonical_ids = {str(attribute.id) for attribute in canonical_attributes}

    for attribute in canonical_attributes:

        attribute.proposed_values = _attribute_effective_values(
            attribute,
            proposal,
        )

        attribute.proposed_fields = _attribute_proposed_fields(
            attribute.id,
            proposal,
        )

        attribute.attribute_proposed = any(attribute.proposed_fields.values())

        attribute.attribute_created = False
        attribute.data_type_choices = AttributeDefinition.DataType.choices

        attributes.append(
            attribute,
        )

    if proposal and relationship_type:

        create_changes = proposal.changes.filter(
            target_type="AttributeDefinition",
            operation=ProposalChange.Operation.CREATE,
            parent_type="RelationshipType",
            parent_id=relationship_type.id,
        ).order_by(
            "created_at",
        )

        for change in create_changes:

            if not change.target_id:
                continue

            if str(change.target_id) in canonical_ids:
                continue

            values = dict(
                change.after or {},
            )

            for update in _attribute_update_changes(
                change.target_id,
                proposal,
            ):
                update_after = update.after or {}
                field = update_after.get("field")

                if (
                    field
                    in ATTRIBUTE_PROPERTY_FIELDS
                    | {
                        ATTRIBUTE_LIFECYCLE_FIELD,
                    }
                    and "value" in update_after
                ):

                    values[field] = update_after["value"]

            attributes.append(
                SimpleNamespace(
                    id=change.target_id,
                    proposed_values={
                        "name": values.get("name", ""),
                        "key": values.get("key", ""),
                        "data_type": values.get(
                            "data_type",
                            AttributeDefinition.DataType.TEXT,
                        ),
                        "description": values.get(
                            "description",
                            "",
                        ),
                        "required": values.get(
                            "required",
                            False,
                        ),
                        "nullable": values.get(
                            "nullable",
                            False,
                        ),
                        "default_value": values.get(
                            "default_value",
                        ),
                        "sort_order": values.get(
                            "sort_order",
                            0,
                        ),
                        "config": values.get("config") or {},
                        "is_active": values.get(
                            "is_active",
                            True,
                        ),
                    },
                    proposed_fields=_attribute_proposed_fields(
                        change.target_id,
                        proposal,
                    ),
                    attribute_proposed=True,
                    attribute_created=True,
                    data_type_choices=(AttributeDefinition.DataType.choices),
                )
            )

    return attributes


# =====================================================================
# Rule helpers
# =====================================================================


def _coerce_rule_type_id(value):
    """
    Rehydrate a subject/object type id read back from proposal JSON
    (stored as a string, see _serialise_rule_value) into a UUID so it
    compares correctly against ObjectType.id elsewhere (view objects,
    templates).
    """

    if isinstance(value, uuid.UUID):
        return value

    if value in (None, ""):
        return value

    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        return value


def _rule_canonical_values(rule):
    return {
        "subject_type_id": rule.subject_type_id,
        "object_type_id": rule.object_type_id,
        "subject_minimum": rule.subject_minimum,
        "subject_maximum": rule.subject_maximum,
        "subject_required": rule.subject_required,
        "object_minimum": rule.object_minimum,
        "object_maximum": rule.object_maximum,
        "object_required": rule.object_required,
    }


def _rule_create_change(
    rule_id,
    proposal,
):
    if not proposal:
        return None

    return (
        proposal.changes.filter(
            target_type="RelationshipTypeRule",
            target_id=rule_id,
            operation=ProposalChange.Operation.CREATE,
        )
        .order_by("created_at")
        .first()
    )


def _rule_effective_values(
    rule,
    proposal,
):
    values = _rule_canonical_values(
        rule,
    )

    if not proposal:
        return values

    for change in proposal.changes.filter(
        target_type="RelationshipTypeRule",
        target_id=rule.id,
        operation=ProposalChange.Operation.UPDATE,
    ).order_by("created_at"):

        after = change.after or {}
        field = after.get("field")

        if field in values and "value" in after:
            values[field] = after["value"]

    values["subject_type_id"] = _coerce_rule_type_id(
        values["subject_type_id"],
    )

    values["object_type_id"] = _coerce_rule_type_id(
        values["object_type_id"],
    )

    return values


def _rule_is_proposed(
    rule_id,
    proposal,
):
    if not proposal:
        return False

    return proposal.changes.filter(
        target_type="RelationshipTypeRule",
        target_id=rule_id,
    ).exists()


def _rule_is_deleted(
    rule_id,
    proposal,
):
    if not proposal:
        return False

    return proposal.changes.filter(
        target_type="RelationshipTypeRule",
        target_id=rule_id,
        operation=ProposalChange.Operation.DELETE,
    ).exists()


def _rule_view_object(
    rule,
    proposal,
    object_type_lookup,
):
    values = _rule_effective_values(
        rule,
        proposal,
    )

    return SimpleNamespace(
        id=rule.id,
        relationship_type_id=rule.relationship_type_id,
        subject_type_id=values["subject_type_id"],
        object_type_id=values["object_type_id"],
        subject_type=object_type_lookup.get(
            str(values["subject_type_id"]),
        ),
        object_type=object_type_lookup.get(
            str(values["object_type_id"]),
        ),
        subject_minimum=values["subject_minimum"],
        subject_maximum=values["subject_maximum"],
        subject_required=values["subject_required"],
        object_minimum=values["object_minimum"],
        object_maximum=values["object_maximum"],
        object_required=values["object_required"],
        is_proposed=_rule_is_proposed(
            rule.id,
            proposal,
        ),
        is_created=False,
        is_deleted=_rule_is_deleted(
            rule.id,
            proposal,
        ),
    )


def _rule_create_values(change):
    after = dict(
        change.after or {},
    )

    return {
        "subject_type_id": _coerce_rule_type_id(
            after.get(
                "subject_type_id",
                after.get("subject_type"),
            ),
        ),
        "object_type_id": _coerce_rule_type_id(
            after.get(
                "object_type_id",
                after.get("object_type"),
            ),
        ),
        "subject_minimum": after.get(
            "subject_minimum",
            0,
        ),
        "subject_maximum": after.get(
            "subject_maximum",
        ),
        "subject_required": after.get(
            "subject_required",
            False,
        ),
        "object_minimum": after.get(
            "object_minimum",
            0,
        ),
        "object_maximum": after.get(
            "object_maximum",
        ),
        "object_required": after.get(
            "object_required",
            False,
        ),
    }


def _rule_create_effective_values(
    rule_id,
    proposal,
):
    create_change = _rule_create_change(
        rule_id,
        proposal,
    )

    if create_change is None:
        return None

    values = _rule_create_values(
        create_change,
    )

    for change in proposal.changes.filter(
        target_type="RelationshipTypeRule",
        target_id=rule_id,
        operation=ProposalChange.Operation.UPDATE,
    ).order_by("created_at"):

        after = change.after or {}
        field = after.get("field")

        if field in values and "value" in after:
            values[field] = after["value"]

    values["subject_type_id"] = _coerce_rule_type_id(
        values["subject_type_id"],
    )

    values["object_type_id"] = _coerce_rule_type_id(
        values["object_type_id"],
    )

    return values


def _build_rule_view_objects(
    relationship_type,
    proposal,
    object_type_lookup,
):
    rules = []

    if isinstance(
        relationship_type,
        RelationshipType,
    ):

        canonical_rules = relationship_type.rules.all().select_related(
            "subject_type",
            "object_type",
        )

        for rule in canonical_rules:

            if _rule_is_deleted(
                rule.id,
                proposal,
            ):
                continue

            rules.append(
                _rule_view_object(
                    rule,
                    proposal,
                    object_type_lookup,
                )
            )

    if proposal and relationship_type:

        create_changes = proposal.changes.filter(
            target_type="RelationshipTypeRule",
            operation=ProposalChange.Operation.CREATE,
            parent_type="RelationshipType",
            parent_id=relationship_type.id,
        ).order_by(
            "created_at",
        )

        for change in create_changes:

            if not change.target_id:
                continue

            values = _rule_create_effective_values(
                change.target_id,
                proposal,
            )

            if values is None:
                continue

            rules.append(
                SimpleNamespace(
                    id=change.target_id,
                    relationship_type_id=relationship_type.id,
                    subject_type_id=values["subject_type_id"],
                    object_type_id=values["object_type_id"],
                    subject_type=object_type_lookup.get(
                        str(values["subject_type_id"]),
                    ),
                    object_type=object_type_lookup.get(
                        str(values["object_type_id"]),
                    ),
                    subject_minimum=values["subject_minimum"],
                    subject_maximum=values["subject_maximum"],
                    subject_required=values["subject_required"],
                    object_minimum=values["object_minimum"],
                    object_maximum=values["object_maximum"],
                    object_required=values["object_required"],
                    is_proposed=True,
                    is_created=True,
                    is_deleted=False,
                )
            )

    return rules


# =====================================================================
# Rule validation
# =====================================================================


def _coerce_rule_integer(
    raw_value,
    label,
    allow_blank=False,
):
    raw_value = str(
        raw_value or "",
    ).strip()

    if not raw_value:

        if allow_blank:
            return None

        raise ValueError(f"{label} is required.")

    try:
        value = int(
            raw_value,
        )

    except (TypeError, ValueError):

        raise ValueError(f"{label} must be a whole number.")

    if value < 0:
        raise ValueError(f"{label} cannot be negative.")

    return value


def _coerce_rule_values(
    request,
):
    subject_type_id = request.POST.get(
        "subject_type_id",
        "",
    ).strip()

    object_type_id = request.POST.get(
        "object_type_id",
        "",
    ).strip()

    if not subject_type_id:
        raise ValueError("Subject object type is required.")

    if not object_type_id:
        raise ValueError("Object object type is required.")

    try:
        subject_type_id = uuid.UUID(
            subject_type_id,
        )
        object_type_id = uuid.UUID(
            object_type_id,
        )
    except ValueError:
        raise ValueError("Invalid object type ID.")

    subject_minimum = _coerce_rule_integer(
        request.POST.get("subject_minimum"),
        "Subject minimum",
    )

    subject_maximum = _coerce_rule_integer(
        request.POST.get("subject_maximum"),
        "Subject maximum",
        allow_blank=True,
    )

    object_minimum = _coerce_rule_integer(
        request.POST.get("object_minimum"),
        "Object minimum",
    )

    object_maximum = _coerce_rule_integer(
        request.POST.get("object_maximum"),
        "Object maximum",
        allow_blank=True,
    )

    subject_required = (
        request.POST.get(
            "subject_required",
        )
        == "on"
    )

    object_required = (
        request.POST.get(
            "object_required",
        )
        == "on"
    )

    if subject_maximum is not None and subject_minimum > subject_maximum:
        raise ValueError("Subject minimum cannot be greater than subject maximum.")

    if object_maximum is not None and object_minimum > object_maximum:
        raise ValueError("Object minimum cannot be greater than object maximum.")

    return {
        "subject_type_id": subject_type_id,
        "object_type_id": object_type_id,
        "subject_minimum": subject_minimum,
        "subject_maximum": subject_maximum,
        "subject_required": subject_required,
        "object_minimum": object_minimum,
        "object_maximum": object_maximum,
        "object_required": object_required,
    }


def _validate_rule_object_types(
    values,
    object_type_lookup,
):
    subject_type_id = str(values["subject_type_id"])

    object_type_id = str(values["object_type_id"])

    if subject_type_id not in object_type_lookup:
        return "The selected subject object type does not exist in the working model."

    if object_type_id not in object_type_lookup:
        return "The selected object object type does not exist in the working model."

    return None


def _serialise_rule_value(value):
    """
    Convert a single coerced rule field value into a JSON-safe value
    for storage in ProposalChange.before/after, preserving integers,
    booleans, and None, and converting UUID instances to strings.
    """

    if isinstance(value, uuid.UUID):
        return str(value)

    return value


def _serialise_rule_values(values):
    return {
        field: _serialise_rule_value(value)
        for field, value in values.items()
    }


# =====================================================================
# Attribute validation helpers
# =====================================================================


def _coerce_default_value(
    data_type,
    raw_value,
):
    raw_value = (raw_value or "").strip()

    if raw_value == "":
        return None

    if data_type == AttributeDefinition.DataType.NUMBER:

        try:

            if "." in raw_value:
                return float(raw_value)

            return int(raw_value)

        except ValueError:
            raise ValueError("Default value must be a number.")

    if data_type == AttributeDefinition.DataType.BOOLEAN:
        return _coerce_boolean(
            raw_value,
            "Default value",
        )

    return raw_value


def _coerce_choices(
    raw_json,
):
    """
    Decode the JSON-encoded attribute_choices POST field into a
    cleaned list of non-blank strings.
    """

    if not raw_json:
        return []

    try:
        parsed = json.loads(raw_json)

    except (TypeError, ValueError):
        raise ValueError("Allowed values could not be read.")

    if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
        raise ValueError("Allowed values must be a list of text options.")

    return [item.strip() for item in parsed if item.strip()]


def _coerce_attribute_properties(
    request,
    existing_values,
):
    name = request.POST.get(
        "attribute_name",
        existing_values.get("name", ""),
    ).strip()

    key = request.POST.get(
        "attribute_key",
        existing_values.get("key", ""),
    ).strip()

    data_type = request.POST.get(
        "attribute_data_type",
        existing_values.get(
            "data_type",
            AttributeDefinition.DataType.TEXT,
        ),
    ).strip()

    description = request.POST.get(
        "attribute_description",
        existing_values.get("description", ""),
    ).strip()

    default_value_raw = request.POST.get(
        "attribute_default_value",
        "",
    )

    required = (
        request.POST.get(
            "attribute_required",
        )
        == "on"
    )

    nullable = (
        request.POST.get(
            "attribute_nullable",
        )
        == "on"
    )

    sort_order_raw = request.POST.get(
        "attribute_sort_order",
        str(
            existing_values.get(
                "sort_order",
                0,
            )
        ),
    ).strip()

    errors = {}

    if not name:
        errors["name"] = "Name is required."

    elif len(name) > 100:
        errors["name"] = "Name cannot exceed 100 characters."

    if not key:
        errors["key"] = "Key is required."

    elif len(key) > 100:
        errors["key"] = "Key cannot exceed 100 characters."

    valid_types = {choice for choice, _label in AttributeDefinition.DataType.choices}

    if data_type not in valid_types:
        errors["data_type"] = "Invalid attribute data type."

    try:
        default_value = _coerce_default_value(
            data_type,
            default_value_raw,
        )

    except ValueError as exc:

        default_value = None
        errors["default_value"] = str(exc)

    try:
        sort_order = int(
            sort_order_raw,
        )

        if sort_order < 0:
            errors["sort_order"] = "Sort order cannot be negative."

    except (TypeError, ValueError):

        sort_order = 0
        errors["sort_order"] = "Sort order must be a whole number."

    # -------------------------------------------------------------
    # Choice configuration
    #
    # data_type is not edited in place elsewhere in this workflow (a
    # different datatype means deleting/recreating the attribute), so
    # this only ever branches on the currently submitted data_type —
    # it never reacts to a datatype transition.
    # -------------------------------------------------------------

    config = {}

    if data_type == AttributeDefinition.DataType.CHOICE:

        if "attribute_choices" not in request.POST:
            # Defensive fallback only — the JS always sends this field
            # for save_attribute/create_attribute. Never treat
            # "missing" as "user cleared the list": preserve whatever
            # this attribute's current effective config already is.
            config = existing_values.get("config") or {}

        else:

            try:
                choices = _coerce_choices(
                    request.POST.get("attribute_choices", ""),
                )

            except ValueError as exc:
                choices = []
                errors["choices"] = str(exc)

            else:

                if not choices:
                    errors["choices"] = "Add at least one allowed value."

                elif len(choices) != len(set(choices)):
                    errors["choices"] = "Allowed values must be unique."

                else:
                    config = {"choices": choices}

    return {
        "name": name,
        "key": key,
        "data_type": data_type,
        "description": description,
        "required": required,
        "nullable": nullable,
        "default_value": default_value,
        "sort_order": sort_order,
        "config": config,
    }, errors


def _validate_attribute_key(
    relationship_type,
    attribute_id,
    key,
):
    if not key:
        return "Key is required."

    query = AttributeDefinition.objects.filter(
        relationship_type=relationship_type,
        key=key,
    )

    if attribute_id:
        query = query.exclude(
            id=attribute_id,
        )

    if query.exists():
        return "An attribute with this key already exists."

    return None


def _validate_proposed_attribute_key(
    proposal,
    relationship_type_id,
    attribute_id,
    key,
):
    if not proposal:
        return None

    create_changes = proposal.changes.filter(
        target_type="AttributeDefinition",
        operation=ProposalChange.Operation.CREATE,
        parent_type="RelationshipType",
        parent_id=relationship_type_id,
    )

    for change in create_changes:

        if str(change.target_id) == str(attribute_id):
            continue

        after = change.after or {}

        if after.get("key") == key:
            return "An attribute with this key already exists."

    return None


# =====================================================================
# Rendering
# =====================================================================


def _build_form(
    values,
    errors=None,
):
    errors = errors or {}

    return {
        "name": {
            "value": values.get("name", ""),
            "errors": errors.get("name"),
        },
        "key": {
            "value": values.get("key", ""),
            "errors": errors.get("key"),
        },
        "description": {
            "value": values.get("description", ""),
            "errors": errors.get("description"),
        },
        "sort_order": {
            "value": values.get("sort_order", 0),
            "errors": errors.get("sort_order"),
        },
        "is_active": {
            "value": values.get("is_active", True),
            "errors": errors.get("is_active"),
        },
    }


def _render_editor(
    *,
    request,
    context,
    model,
    relationship_type,
    proposal,
    effective_values,
    errors=None,
):
    object_type_lookup = {
        str(object_type.id): object_type
        for object_type in context.get(
            "object_types",
            [],
        )
    }

    context.update(
        {
            "relationship_type": relationship_type,
            "proposal": proposal,
            "proposed_values": effective_values,
            "proposed_fields": (
                _relationship_type_proposed_fields(
                    relationship_type.id,
                    proposal,
                )
                if relationship_type
                else {}
            ),
            "attributes": (
                _build_attribute_view_objects(
                    relationship_type,
                    proposal,
                )
                if relationship_type
                else []
            ),
            "rules": (
                _build_rule_view_objects(
                    relationship_type,
                    proposal,
                    object_type_lookup,
                )
                if relationship_type
                else []
            ),
            "working_object_types": context.get(
                "object_types",
                [],
            ),
            "form": _build_form(
                effective_values,
                errors,
            ),
            "proposal_update_url": request.path,
            "attribute_data_types": (AttributeDefinition.DataType.choices),
        }
    )

    return render(
        request,
        "model/relationship_type_editor.html",
        context,
    )


# =====================================================================
# Main view
# =====================================================================


@login_required
def relationship_type_editor(
    request,
    model_id,
    relationship_type_id=None,
):
    context = get_model_context(
        request,
        model_id,
    )

    model = context["model"]
    proposal = context["my_working_proposal"]

    working_object_types = context.get(
        "object_types",
        [],
    )

    object_type_lookup = {
        str(object_type.id): object_type for object_type in working_object_types
    }

    relationship_type = None
    proposal_only = False

    if relationship_type_id:

        relationship_type = RelationshipType.objects.filter(
            id=relationship_type_id,
            model=model,
        ).first()

        if relationship_type is None:

            relationship_type = context_relationship_type if False else None

            if proposal:
                relationship_type = _relationship_type_proposed_only(
                    relationship_type_id,
                    proposal,
                )

            if relationship_type is None:
                raise Http404("Relationship type not found.")

            proposal_only = True

    # =================================================================
    # RelationshipType lifecycle
    # =================================================================

    if (
        request.method == "POST"
        and request.POST.get("action") == "set_relationship_type_status"
    ):

        if relationship_type is None:
            return JsonResponse(
                {
                    "success": False,
                    "error": "Relationship type not found.",
                },
                status=404,
            )

        try:
            desired_active = _coerce_boolean(
                request.POST.get(
                    "is_active",
                    "",
                ),
                "Status",
            )

        except ValueError as exc:
            return JsonResponse(
                {
                    "success": False,
                    "error": str(exc),
                },
                status=400,
            )

        if proposal is None:
            proposal = _working_proposal(
                model,
                request.user,
            )

        if proposal_only:

            create_change = _relationship_type_create_change(
                relationship_type.id,
                proposal,
            )

            if create_change is None:
                return JsonResponse(
                    {
                        "success": False,
                        "error": "Proposed relationship type not found.",
                    },
                    status=404,
                )

            after = dict(
                create_change.after or {},
            )

            after["is_active"] = desired_active

            create_change.after = after

            create_change.save(
                update_fields=[
                    "after",
                    "updated_at",
                ]
            )

            ProposalService.reset_validation(
                proposal,
            )

            return JsonResponse(
                {
                    "success": True,
                    "value": _serialize_value(
                        desired_active,
                    ),
                    "proposed": True,
                }
            )

        canonical_active = relationship_type.is_active

        if desired_active == canonical_active:

            if proposal:
                ProposalService.discard_change(
                    proposal=proposal,
                    target_type="RelationshipType",
                    target_id=relationship_type.id,
                    field="is_active",
                )

            return JsonResponse(
                {
                    "success": True,
                    "value": _serialize_value(
                        canonical_active,
                    ),
                    "proposed": (
                        _relationship_type_proposed_fields(
                            relationship_type.id,
                            proposal,
                        )["is_active"]
                    ),
                }
            )

        ProposalService.record_change(
            proposal=proposal,
            operation=ProposalChange.Operation.UPDATE,
            target_type="RelationshipType",
            target_id=relationship_type.id,
            parent_type="Model",
            parent_id=model.id,
            field="is_active",
            before={
                "field": "is_active",
                "value": canonical_active,
            },
            after={
                "field": "is_active",
                "value": desired_active,
            },
        )

        return JsonResponse(
            {
                "success": True,
                "value": _serialize_value(
                    desired_active,
                ),
                "proposed": True,
            }
        )

    # =================================================================
    # RelationshipType lifecycle discard
    # =================================================================

    if (
        request.method == "POST"
        and request.POST.get("action") == "discard_relationship_type_status"
    ):

        if relationship_type is None:
            return JsonResponse(
                {
                    "success": False,
                    "error": "Relationship type not found.",
                },
                status=404,
            )

        if proposal is None:
            return JsonResponse(
                {
                    "success": False,
                    "error": "There is no working proposal to discard.",
                },
                status=400,
            )

        if proposal_only:
            return JsonResponse(
                {
                    "success": False,
                    "error": (
                        "The lifecycle of a newly proposed "
                        "Relationship Type cannot be independently "
                        "discarded."
                    ),
                },
                status=400,
            )

        ProposalService.discard_change(
            proposal=proposal,
            target_type="RelationshipType",
            target_id=relationship_type.id,
            field="is_active",
        )

        return JsonResponse(
            {
                "success": True,
                "value": _serialize_value(
                    relationship_type.is_active,
                ),
                "proposed": False,
            }
        )

    # =================================================================
    # Relationship Type property editing
    # =================================================================

    if request.method == "POST" and request.POST.get("field"):

        if relationship_type is None:
            return JsonResponse(
                {
                    "success": False,
                    "error": "Relationship type not found.",
                },
                status=404,
            )

        field = request.POST.get(
            "field",
            "",
        ).strip()

        if field not in RELATIONSHIP_TYPE_PROPERTY_FIELDS:
            return JsonResponse(
                {
                    "success": False,
                    "error": "Unsupported field.",
                },
                status=400,
            )

        action = request.POST.get(
            "action",
            "",
        ).strip()

        if action == "discard":

            if proposal is None:
                return JsonResponse(
                    {
                        "success": False,
                        "error": ("There is no working proposal to discard."),
                    },
                    status=400,
                )

            if proposal_only:
                return JsonResponse(
                    {
                        "success": False,
                        "error": (
                            "Individual property discard is not "
                            "available for a newly proposed "
                            "Relationship Type."
                        ),
                    },
                    status=400,
                )

            ProposalService.discard_change(
                proposal=proposal,
                target_type="RelationshipType",
                target_id=relationship_type.id,
                field=field,
            )

            return JsonResponse(
                {
                    "success": True,
                    "value": _serialize_value(
                        getattr(
                            relationship_type,
                            field,
                        )
                    ),
                    "proposed": False,
                }
            )

        if action:
            return JsonResponse(
                {
                    "success": False,
                    "error": "Invalid action.",
                },
                status=400,
            )

        value = request.POST.get(
            "value",
            "",
        ).strip()

        if field in {
            "name",
            "key",
            "description",
        }:

            if field == "name" and not value:
                return JsonResponse(
                    {
                        "success": False,
                        "error": "Name is required.",
                    },
                    status=400,
                )

            if len(value) > 100:
                return JsonResponse(
                    {
                        "success": False,
                        "error": (f"{field.title()} cannot exceed " "100 characters."),
                    },
                    status=400,
                )

        elif field == "sort_order":

            try:
                value = int(value)

            except (TypeError, ValueError):
                return JsonResponse(
                    {
                        "success": False,
                        "error": ("Sort order must be a whole number."),
                    },
                    status=400,
                )

            if value < 0:
                return JsonResponse(
                    {
                        "success": False,
                        "error": ("Sort order cannot be negative."),
                    },
                    status=400,
                )

        if field == "key":

            query = RelationshipType.objects.filter(
                model=model,
                key=value,
            )

            if isinstance(
                relationship_type,
                RelationshipType,
            ):
                query = query.exclude(
                    id=relationship_type.id,
                )

            if query.exists():
                return JsonResponse(
                    {
                        "success": False,
                        "error": (
                            "A relationship type with this " "key already exists."
                        ),
                    },
                    status=400,
                )

            # Also check proposed RelationshipType CREATEs/updates.
            if proposal:

                for change in proposal.changes.filter(
                    target_type="RelationshipType",
                ):

                    if not isinstance(change.after, dict) or str(
                        change.target_id
                    ) == str(relationship_type.id):
                        continue

                    after = change.after or {}

                    if change.operation == (ProposalChange.Operation.CREATE):
                        proposed_key = after.get(
                            "key",
                        )

                    elif change.operation == (ProposalChange.Operation.UPDATE):
                        if after.get("field") != "key":
                            continue

                        proposed_key = after.get(
                            "value",
                        )

                    else:
                        continue

                    if proposed_key == value:
                        return JsonResponse(
                            {
                                "success": False,
                                "error": (
                                    "A relationship type with "
                                    "this key already exists "
                                    "in the working proposal."
                                ),
                            },
                            status=400,
                        )

        if proposal is None:
            proposal = _working_proposal(
                model,
                request.user,
            )

        if proposal_only:

            create_change = _relationship_type_create_change(
                relationship_type.id,
                proposal,
            )

            if create_change is None:
                return JsonResponse(
                    {
                        "success": False,
                        "error": ("Proposed relationship type not found."),
                    },
                    status=404,
                )

            after = dict(
                create_change.after or {},
            )

            after[field] = value
            create_change.after = after

            create_change.save(
                update_fields=[
                    "after",
                    "updated_at",
                ]
            )

            ProposalService.reset_validation(
                proposal,
            )

            return JsonResponse(
                {
                    "success": True,
                    "value": _serialize_value(value),
                    "proposed": True,
                }
            )

        canonical_value = getattr(
            relationship_type,
            field,
        )

        if value == canonical_value:

            ProposalService.discard_change(
                proposal=proposal,
                target_type="RelationshipType",
                target_id=relationship_type.id,
                field=field,
            )

            return JsonResponse(
                {
                    "success": True,
                    "value": _serialize_value(
                        canonical_value,
                    ),
                    "proposed": False,
                }
            )

        ProposalService.record_change(
            proposal=proposal,
            operation=ProposalChange.Operation.UPDATE,
            target_type="RelationshipType",
            target_id=relationship_type.id,
            parent_type="Model",
            parent_id=model.id,
            field=field,
            before={
                "field": field,
                "value": canonical_value,
            },
            after={
                "field": field,
                "value": value,
            },
        )

        return JsonResponse(
            {
                "success": True,
                "value": _serialize_value(value),
                "proposed": True,
            }
        )

    # =================================================================
    # Create RelationshipType
    # =================================================================

    if (
        request.method == "POST"
        and request.POST.get("action") == "create_relationship_type"
    ):

        name = request.POST.get(
            "name",
            "",
        ).strip()

        key = request.POST.get(
            "key",
            "",
        ).strip()

        description = request.POST.get(
            "description",
            "",
        ).strip()

        errors = {}

        if not name:
            errors["name"] = "Name is required."

        elif len(name) > 100:
            errors["name"] = "Name cannot exceed 100 characters."

        if not key:
            errors["key"] = "Key is required."

        elif len(key) > 100:
            errors["key"] = "Key cannot exceed 100 characters."

        if RelationshipType.objects.filter(
            model=model,
            key=key,
        ).exists():
            errors["key"] = "A relationship type with this key already exists."

        if errors:
            return _render_editor(
                request=request,
                context=context,
                model=model,
                relationship_type=None,
                proposal=proposal,
                effective_values={
                    "name": name,
                    "key": key,
                    "description": description,
                    "sort_order": 0,
                    "is_active": True,
                },
                errors=errors,
            )

        proposal = proposal or _working_proposal(
            model,
            request.user,
        )

        relationship_type_uuid = uuid.uuid4()

        ProposalService.record_change(
            proposal=proposal,
            operation=ProposalChange.Operation.CREATE,
            target_type="RelationshipType",
            target_id=relationship_type_uuid,
            parent_type="Model",
            parent_id=model.id,
            before=None,
            after={
                "name": name,
                "key": key,
                "description": description,
                "sort_order": 0,
                "is_active": True,
            },
        )

        return redirect(
            "model:relationship_type_edit",
            model.id,
            relationship_type_uuid,
        )

    # =================================================================
    # Create AttributeDefinition
    # =================================================================

    if request.method == "POST" and request.POST.get("action") == "create_attribute":

        if relationship_type is None:
            return JsonResponse(
                {
                    "success": False,
                    "error": "Relationship type not found.",
                },
                status=404,
            )

        if proposal is None:
            proposal = _working_proposal(
                model,
                request.user,
            )

        submitted_values, errors = _coerce_attribute_properties(
            request,
            {
                "name": "",
                "key": "",
                "data_type": AttributeDefinition.DataType.TEXT,
                "description": "",
                "required": False,
                "nullable": False,
                "default_value": None,
                "sort_order": 0,
                "config": {},
            },
        )

        if isinstance(
            relationship_type,
            RelationshipType,
        ):

            canonical_key_error = _validate_attribute_key(
                relationship_type,
                None,
                submitted_values["key"],
            )

            if canonical_key_error:
                errors["key"] = canonical_key_error

        proposed_key_error = _validate_proposed_attribute_key(
            proposal=proposal,
            relationship_type_id=relationship_type.id,
            attribute_id=None,
            key=submitted_values["key"],
        )

        if proposed_key_error:
            errors["key"] = proposed_key_error

        if errors:
            return JsonResponse(
                {
                    "success": False,
                    "errors": errors,
                    "error": "Please correct the attribute before adding it.",
                },
                status=400,
            )

        attribute_uuid = uuid.uuid4()

        ProposalService.record_change(
            proposal=proposal,
            operation=ProposalChange.Operation.CREATE,
            target_type="AttributeDefinition",
            target_id=attribute_uuid,
            parent_type="RelationshipType",
            parent_id=relationship_type.id,
            before=None,
            after={
                **submitted_values,
                "is_active": True,
            },
        )

        values = {
            **submitted_values,
            "is_active": True,
        }

        return JsonResponse(
            {
                "success": True,
                "created": True,
                "attribute_id": str(attribute_uuid),
                "values": {
                    field: _serialize_value(
                        values[field],
                    )
                    for field in (
                        *ATTRIBUTE_PROPERTY_FIELDS,
                        ATTRIBUTE_LIFECYCLE_FIELD,
                    )
                },
                "proposed": True,
                "proposed_fields": {
                    field: True
                    for field in (
                        *ATTRIBUTE_PROPERTY_FIELDS,
                        ATTRIBUTE_LIFECYCLE_FIELD,
                    )
                },
            }
        )

    # =================================================================
    # Save AttributeDefinition properties
    # =================================================================

    if request.method == "POST" and request.POST.get("action") == "save_attribute":

        if relationship_type is None:
            return JsonResponse(
                {
                    "success": False,
                    "error": "Relationship type not found.",
                },
                status=404,
            )

        attribute_id = request.POST.get(
            "attribute_id",
        )

        if not attribute_id:
            return JsonResponse(
                {
                    "success": False,
                    "error": "Attribute ID is required.",
                },
                status=400,
            )

        try:
            attribute_uuid = uuid.UUID(
                attribute_id,
            )

        except ValueError:
            return JsonResponse(
                {
                    "success": False,
                    "error": "Invalid attribute ID.",
                },
                status=400,
            )

        (
            attribute,
            effective_values,
            attribute_created,
        ) = _attribute_proposal_values(
            attribute_uuid,
            (
                relationship_type
                if isinstance(
                    relationship_type,
                    RelationshipType,
                )
                else None
            ),
            proposal,
        )

        if effective_values is None:
            return JsonResponse(
                {
                    "success": False,
                    "error": "Attribute not found.",
                },
                status=404,
            )

        submitted_values, errors = _coerce_attribute_properties(
            request,
            effective_values,
        )

        if isinstance(
            relationship_type,
            RelationshipType,
        ):

            key_error = _validate_attribute_key(
                relationship_type,
                (None if attribute_created else attribute_uuid),
                submitted_values["key"],
            )

            if key_error:
                errors["key"] = key_error

        if proposal:

            proposed_key_error = _validate_proposed_attribute_key(
                proposal=proposal,
                relationship_type_id=relationship_type.id,
                attribute_id=attribute_uuid,
                key=submitted_values["key"],
            )

            if proposed_key_error:
                errors["key"] = proposed_key_error

        if errors:
            return JsonResponse(
                {
                    "success": False,
                    "errors": errors,
                    "error": "Please correct the attribute before saving.",
                },
                status=400,
            )

        if proposal is None:
            proposal = _working_proposal(
                model,
                request.user,
            )

        if attribute_created:

            create_change = _attribute_create_change(
                attribute_uuid,
                proposal,
            )

            if create_change is None:
                return JsonResponse(
                    {
                        "success": False,
                        "error": "Proposed attribute not found.",
                    },
                    status=404,
                )

            after = dict(
                create_change.after or {},
            )

            after.update(
                submitted_values,
            )

            after.setdefault(
                "is_active",
                True,
            )

            create_change.after = after

            create_change.save(
                update_fields=[
                    "after",
                    "updated_at",
                ]
            )

            ProposalService.reset_validation(
                proposal,
            )

        else:

            canonical_values = _attribute_canonical_values(
                attribute,
            )

            for field in ATTRIBUTE_PROPERTY_FIELDS:

                canonical_value = canonical_values[field]
                submitted_value = submitted_values[field]

                if submitted_value == canonical_value:

                    ProposalService.discard_change(
                        proposal=proposal,
                        target_type="AttributeDefinition",
                        target_id=attribute_uuid,
                        field=field,
                    )

                    continue

                ProposalService.record_change(
                    proposal=proposal,
                    operation=ProposalChange.Operation.UPDATE,
                    target_type="AttributeDefinition",
                    target_id=attribute_uuid,
                    parent_type="RelationshipType",
                    parent_id=relationship_type.id,
                    field=field,
                    before={
                        "field": field,
                        "value": canonical_value,
                    },
                    after={
                        "field": field,
                        "value": submitted_value,
                    },
                )

        (
            _attribute,
            effective_values,
            attribute_created,
        ) = _attribute_proposal_values(
            attribute_uuid,
            (
                relationship_type
                if isinstance(
                    relationship_type,
                    RelationshipType,
                )
                else None
            ),
            proposal,
        )

        return JsonResponse(
            {
                "success": True,
                "attribute_id": str(
                    attribute_uuid,
                ),
                "values": {
                    field: _serialize_value(effective_values[field])
                    for field in (
                        *ATTRIBUTE_PROPERTY_FIELDS,
                        ATTRIBUTE_LIFECYCLE_FIELD,
                    )
                },
                "proposed": (
                    _attribute_is_proposed(
                        attribute_uuid,
                        proposal,
                    )
                ),
                "proposed_fields": (
                    _attribute_proposed_fields(
                        attribute_uuid,
                        proposal,
                    )
                ),
                "created": attribute_created,
            }
        )

    # =================================================================
    # Discard AttributeDefinition proposal
    # =================================================================

    if request.method == "POST" and request.POST.get("action") == "discard_attribute":

        if relationship_type is None:
            return JsonResponse(
                {
                    "success": False,
                    "error": "Relationship type not found.",
                },
                status=404,
            )

        attribute_id = request.POST.get(
            "attribute_id",
        )

        if not attribute_id:
            return JsonResponse(
                {
                    "success": False,
                    "error": "Attribute ID is required.",
                },
                status=400,
            )

        try:
            attribute_uuid = uuid.UUID(
                attribute_id,
            )

        except ValueError:
            return JsonResponse(
                {
                    "success": False,
                    "error": "Invalid attribute ID.",
                },
                status=400,
            )

        if proposal is None:
            return JsonResponse(
                {
                    "success": False,
                    "error": "There is no working proposal to discard.",
                },
                status=400,
            )

        (
            attribute,
            effective_values,
            attribute_created,
        ) = _attribute_proposal_values(
            attribute_uuid,
            (
                relationship_type
                if isinstance(
                    relationship_type,
                    RelationshipType,
                )
                else None
            ),
            proposal,
        )

        if effective_values is None:
            return JsonResponse(
                {
                    "success": False,
                    "error": "Attribute not found.",
                },
                status=404,
            )

        ProposalService.discard_change(
            proposal=proposal,
            target_type="AttributeDefinition",
            target_id=attribute_uuid,
        )

        if attribute_created:
            return JsonResponse(
                {
                    "success": True,
                    "removed": True,
                    "attribute_id": str(
                        attribute_uuid,
                    ),
                }
            )

        canonical_values = _attribute_canonical_values(
            attribute,
        )

        return JsonResponse(
            {
                "success": True,
                "removed": False,
                "attribute_id": str(
                    attribute_uuid,
                ),
                "values": {
                    field: _serialize_value(canonical_values[field])
                    for field in (
                        *ATTRIBUTE_PROPERTY_FIELDS,
                        ATTRIBUTE_LIFECYCLE_FIELD,
                    )
                },
                "proposed": False,
                "proposed_fields": {
                    field: False
                    for field in (
                        *ATTRIBUTE_PROPERTY_FIELDS,
                        ATTRIBUTE_LIFECYCLE_FIELD,
                    )
                },
            }
        )

    # =================================================================
    # Attribute lifecycle
    # =================================================================

    if (
        request.method == "POST"
        and request.POST.get("action") == "set_attribute_status"
    ):

        if relationship_type is None:
            return JsonResponse(
                {
                    "success": False,
                    "error": "Relationship type not found.",
                },
                status=404,
            )

        attribute_id = request.POST.get(
            "attribute_id",
        )

        if not attribute_id:
            return JsonResponse(
                {
                    "success": False,
                    "error": "Attribute ID is required.",
                },
                status=400,
            )

        try:
            attribute_uuid = uuid.UUID(
                attribute_id,
            )

        except ValueError:
            return JsonResponse(
                {
                    "success": False,
                    "error": "Invalid attribute ID.",
                },
                status=400,
            )

        (
            attribute,
            effective_values,
            attribute_created,
        ) = _attribute_proposal_values(
            attribute_uuid,
            (
                relationship_type
                if isinstance(
                    relationship_type,
                    RelationshipType,
                )
                else None
            ),
            proposal,
        )

        if effective_values is None:
            return JsonResponse(
                {
                    "success": False,
                    "error": "Attribute not found.",
                },
                status=404,
            )

        try:
            desired_active = _coerce_boolean(
                request.POST.get(
                    "is_active",
                    "",
                ),
                "Status",
            )

        except ValueError as exc:
            return JsonResponse(
                {
                    "success": False,
                    "error": str(exc),
                },
                status=400,
            )

        if proposal is None:
            proposal = _working_proposal(
                model,
                request.user,
            )

        if attribute_created:

            create_change = _attribute_create_change(
                attribute_uuid,
                proposal,
            )

            if create_change is None:
                return JsonResponse(
                    {
                        "success": False,
                        "error": "Proposed attribute not found.",
                    },
                    status=404,
                )

            after = dict(
                create_change.after or {},
            )

            after["is_active"] = desired_active

            create_change.after = after

            create_change.save(
                update_fields=[
                    "after",
                    "updated_at",
                ]
            )

            ProposalService.reset_validation(
                proposal,
            )

            return JsonResponse(
                {
                    "success": True,
                    "value": _serialize_value(
                        desired_active,
                    ),
                    "proposed": True,
                    "proposed_fields": (
                        _attribute_proposed_fields(
                            attribute_uuid,
                            proposal,
                        )
                    ),
                }
            )

        canonical_active = attribute.is_active

        if desired_active == canonical_active:

            ProposalService.discard_change(
                proposal=proposal,
                target_type="AttributeDefinition",
                target_id=attribute_uuid,
                field="is_active",
            )

            return JsonResponse(
                {
                    "success": True,
                    "value": _serialize_value(
                        canonical_active,
                    ),
                    "proposed": (
                        _attribute_is_proposed(
                            attribute_uuid,
                            proposal,
                        )
                    ),
                    "proposed_fields": (
                        _attribute_proposed_fields(
                            attribute_uuid,
                            proposal,
                        )
                    ),
                }
            )

        ProposalService.record_change(
            proposal=proposal,
            operation=ProposalChange.Operation.UPDATE,
            target_type="AttributeDefinition",
            target_id=attribute_uuid,
            parent_type="RelationshipType",
            parent_id=relationship_type.id,
            field="is_active",
            before={
                "field": "is_active",
                "value": canonical_active,
            },
            after={
                "field": "is_active",
                "value": desired_active,
            },
        )

        return JsonResponse(
            {
                "success": True,
                "value": _serialize_value(
                    desired_active,
                ),
                "proposed": True,
                "proposed_fields": (
                    _attribute_proposed_fields(
                        attribute_uuid,
                        proposal,
                    )
                ),
            }
        )

    # =================================================================
    # Create Rule
    # =================================================================

    if request.method == "POST" and request.POST.get("action") == "create_rule":

        if relationship_type is None:
            return JsonResponse(
                {
                    "success": False,
                    "error": "Relationship type not found.",
                },
                status=404,
            )

        proposal = proposal or _working_proposal(
            model,
            request.user,
        )

        try:
            values = _coerce_rule_values(
                request,
            )

        except ValueError as exc:

            return JsonResponse(
                {
                    "success": False,
                    "error": str(exc),
                },
                status=400,
            )

        error = _validate_rule_object_types(
            values,
            object_type_lookup,
        )

        if error:
            return JsonResponse(
                {
                    "success": False,
                    "error": error,
                },
                status=400,
            )

        # -------------------------------------------------------------
        # Prevent duplicate rule combinations in the working model.
        # -------------------------------------------------------------

        for existing_rule in _build_rule_view_objects(
            relationship_type,
            proposal,
            object_type_lookup,
        ):

            if str(existing_rule.subject_type_id) == str(
                values["subject_type_id"]
            ) and str(existing_rule.object_type_id) == str(values["object_type_id"]):
                return JsonResponse(
                    {
                        "success": False,
                        "error": (
                            "A rule already exists for this "
                            "subject and object type combination."
                        ),
                    },
                    status=400,
                )

        rule_uuid = uuid.uuid4()

        ProposalService.record_change(
            proposal=proposal,
            operation=ProposalChange.Operation.CREATE,
            target_type="RelationshipTypeRule",
            target_id=rule_uuid,
            parent_type="RelationshipType",
            parent_id=relationship_type.id,
            before=None,
            after=_serialise_rule_values(values),
        )

        return JsonResponse(
            {
                "success": True,
                "created": True,
                "rule_id": str(rule_uuid),
                "values": {
                    field: _serialize_value(
                        values[field],
                    )
                    for field in RULE_FIELDS
                },
            }
        )

    # =================================================================
    # Save Rule
    # =================================================================

    if request.method == "POST" and request.POST.get("action") == "save_rule":

        if relationship_type is None:
            return JsonResponse(
                {
                    "success": False,
                    "error": "Relationship type not found.",
                },
                status=404,
            )

        rule_id = request.POST.get(
            "rule_id",
            "",
        ).strip()

        if not rule_id:
            return JsonResponse(
                {
                    "success": False,
                    "error": "Rule ID is required.",
                },
                status=400,
            )

        try:
            rule_uuid = uuid.UUID(
                rule_id,
            )

        except ValueError:
            return JsonResponse(
                {
                    "success": False,
                    "error": "Invalid rule ID.",
                },
                status=400,
            )

        proposal = proposal or _working_proposal(
            model,
            request.user,
        )

        canonical_rule = RelationshipTypeRule.objects.filter(
            id=rule_uuid,
            relationship_type=relationship_type,
        ).first()

        if canonical_rule:

            existing_values = _rule_effective_values(
                canonical_rule,
                proposal,
            )

            is_created = False

        else:

            existing_values = _rule_create_effective_values(
                rule_uuid,
                proposal,
            )

            if existing_values is None:
                return JsonResponse(
                    {
                        "success": False,
                        "error": "Rule not found.",
                    },
                    status=404,
                )

            is_created = True

        try:
            values = _coerce_rule_values(
                request,
            )

        except ValueError as exc:

            return JsonResponse(
                {
                    "success": False,
                    "error": str(exc),
                },
                status=400,
            )

        error = _validate_rule_object_types(
            values,
            object_type_lookup,
        )

        if error:
            return JsonResponse(
                {
                    "success": False,
                    "error": error,
                },
                status=400,
            )

        # -------------------------------------------------------------
        # Duplicate subject/object combination check.
        # -------------------------------------------------------------

        for existing_rule in _build_rule_view_objects(
            relationship_type,
            proposal,
            object_type_lookup,
        ):

            if str(existing_rule.id) == str(rule_uuid):
                continue

            if str(existing_rule.subject_type_id) == str(
                values["subject_type_id"]
            ) and str(existing_rule.object_type_id) == str(values["object_type_id"]):
                return JsonResponse(
                    {
                        "success": False,
                        "error": (
                            "A rule already exists for this "
                            "subject and object type combination."
                        ),
                    },
                    status=400,
                )

        if is_created:

            create_change = _rule_create_change(
                rule_uuid,
                proposal,
            )

            if create_change is None:
                return JsonResponse(
                    {
                        "success": False,
                        "error": "Proposed rule not found.",
                    },
                    status=404,
                )

            create_change.after = _serialise_rule_values(values)

            create_change.save(
                update_fields=[
                    "after",
                    "updated_at",
                ]
            )

            ProposalService.reset_validation(
                proposal,
            )

        else:

            for field in RULE_FIELDS:

                canonical_value = _rule_canonical_values(
                    canonical_rule,
                )[field]

                submitted_value = values[field]

                if submitted_value == canonical_value:

                    ProposalService.discard_change(
                        proposal=proposal,
                        target_type="RelationshipTypeRule",
                        target_id=rule_uuid,
                        field=field,
                    )

                    continue

                ProposalService.record_change(
                    proposal=proposal,
                    operation=ProposalChange.Operation.UPDATE,
                    target_type="RelationshipTypeRule",
                    target_id=rule_uuid,
                    parent_type="RelationshipType",
                    parent_id=relationship_type.id,
                    field=field,
                    before={
                        "field": field,
                        "value": _serialise_rule_value(canonical_value),
                    },
                    after={
                        "field": field,
                        "value": _serialise_rule_value(submitted_value),
                    },
                )

        return JsonResponse(
            {
                "success": True,
                "rule_id": str(rule_uuid),
                "values": {
                    field: _serialize_value(
                        values[field],
                    )
                    for field in RULE_FIELDS
                },
                "proposed": True,
            }
        )

    # =================================================================
    # Discard Rule
    # =================================================================

    if request.method == "POST" and request.POST.get("action") == "discard_rule":

        if relationship_type is None:
            return JsonResponse(
                {
                    "success": False,
                    "error": "Relationship type not found.",
                },
                status=404,
            )

        rule_id = request.POST.get(
            "rule_id",
            "",
        ).strip()

        try:
            rule_uuid = uuid.UUID(
                rule_id,
            )

        except ValueError:
            return JsonResponse(
                {
                    "success": False,
                    "error": "Invalid rule ID.",
                },
                status=400,
            )

        if proposal is None:
            return JsonResponse(
                {
                    "success": False,
                    "error": "There is no working proposal to discard.",
                },
                status=400,
            )

        canonical_rule = RelationshipTypeRule.objects.filter(
            id=rule_uuid,
            relationship_type=relationship_type,
        ).first()

        ProposalService.discard_change(
            proposal=proposal,
            target_type="RelationshipTypeRule",
            target_id=rule_uuid,
        )

        if canonical_rule is None:

            return JsonResponse(
                {
                    "success": True,
                    "removed": True,
                    "rule_id": str(rule_uuid),
                }
            )

        return JsonResponse(
            {
                "success": True,
                "removed": False,
                "rule_id": str(rule_uuid),
                "values": {
                    field: _serialize_value(
                        _rule_canonical_values(
                            canonical_rule,
                        )[field]
                    )
                    for field in RULE_FIELDS
                },
                "proposed": False,
            }
        )

    # =================================================================
    # Standard GET
    # =================================================================

    if relationship_type is None:

        effective_values = {
            "name": "",
            "key": "",
            "description": "",
            "sort_order": 0,
            "is_active": True,
        }

    else:

        if proposal_only:

            effective_values = {
                "name": relationship_type.name,
                "key": relationship_type.key,
                "description": relationship_type.description,
                "sort_order": relationship_type.sort_order,
                "is_active": relationship_type.is_active,
            }

        else:

            effective_values = {
                "name": relationship_type.name,
                "key": relationship_type.key,
                "description": relationship_type.description,
                "sort_order": relationship_type.sort_order,
                "is_active": relationship_type.is_active,
            }

            # Overlay any working changes when the canonical object is
            # being used as the editor target.
            if proposal:

                for change in proposal.changes.filter(
                    target_type="RelationshipType",
                    target_id=relationship_type.id,
                    operation=ProposalChange.Operation.UPDATE,
                ).order_by("created_at"):

                    after = change.after or {}
                    field = after.get("field")

                    if field in effective_values and "value" in after:
                        effective_values[field] = after["value"]

    return _render_editor(
        request=request,
        context=context,
        model=model,
        relationship_type=relationship_type,
        proposal=proposal,
        effective_values=effective_values,
    )
