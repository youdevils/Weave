import uuid

from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render

from model.models.attribute_definition import AttributeDefinition
from model.models.object_type import ObjectType
from model.models.proposal import ProposalChange
from model.services.proposal.proposal import ProposalService
from model.views.common_context import get_model_context

# =====================================================================
# Fields
# =====================================================================

OBJECT_TYPE_FIELDS = {
    "name",
    "key",
    "description",
    "sort_order",
    "is_active",
}


ATTRIBUTE_FIELDS = {
    "name",
    "key",
    "data_type",
    "description",
    "required",
    "nullable",
    "default_value",
    "sort_order",
    "is_active",
}


# =====================================================================
# ObjectType state
# =====================================================================


def _object_type_canonical_values(object_type):
    return {
        "name": object_type.name,
        "key": object_type.key,
        "description": object_type.description,
        "sort_order": object_type.sort_order,
        "is_active": object_type.is_active,
    }


def _object_type_effective_values(
    object_type,
    proposal,
):
    values = _object_type_canonical_values(
        object_type,
    )

    if not proposal:
        return values

    changes = proposal.changes.filter(
        target_type="ObjectType",
        target_id=object_type.id,
        operation=ProposalChange.Operation.UPDATE,
    ).order_by("created_at")

    for change in changes:
        after = change.after or {}
        field = after.get("field")

        if field in values and "value" in after:
            values[field] = after["value"]

    return values


def _object_type_proposed_fields(
    object_type,
    proposal,
):
    result = {field: False for field in OBJECT_TYPE_FIELDS}

    if not proposal:
        return result

    changes = proposal.changes.filter(
        target_type="ObjectType",
        target_id=object_type.id,
        operation=ProposalChange.Operation.UPDATE,
    ).order_by("created_at")

    for change in changes:
        after = change.after or {}
        field = after.get("field")

        if field in result:
            result[field] = True

    return result


# =====================================================================
# Attribute state
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
    object_type,
    proposal,
):
    """
    Resolve an attribute that may be either:

    - an existing canonical AttributeDefinition, or
    - a CREATE proposal which does not exist canonically yet.
    """

    attribute = AttributeDefinition.objects.filter(
        id=attribute_id,
        object_type=object_type,
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

    if not create_change:
        return None, None, False

    after = create_change.after or {}

    values = {
        "name": after.get(
            "name",
            "",
        ),
        "key": after.get(
            "key",
            "",
        ),
        "data_type": after.get(
            "data_type",
            AttributeDefinition.DataType.TEXT,
        ),
        "description": after.get(
            "description",
            "",
        ),
        "required": after.get(
            "required",
            False,
        ),
        "nullable": after.get(
            "nullable",
            False,
        ),
        "default_value": after.get(
            "default_value",
            None,
        ),
        "sort_order": after.get(
            "sort_order",
            0,
        ),
        "is_active": after.get(
            "is_active",
            True,
        ),
    }

    for change in _attribute_update_changes(
        attribute_id,
        proposal,
    ):
        after_update = change.after or {}
        field = after_update.get("field")

        if field in values and "value" in after_update:
            values[field] = after_update["value"]

    return None, values, True


def _attribute_proposed_fields(
    attribute_id,
    proposal,
):
    result = {field: False for field in ATTRIBUTE_FIELDS}

    if not proposal:
        return result

    changes = proposal.changes.filter(
        target_type="AttributeDefinition",
        target_id=attribute_id,
    ).order_by("created_at")

    for change in changes:

        if change.operation == (ProposalChange.Operation.CREATE):
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


def _get_canonical_attributes(
    object_type,
):
    return list(
        AttributeDefinition.objects.filter(
            object_type=object_type,
        ).order_by(
            "sort_order",
            "name",
        )
    )


def _build_attribute_view_objects(
    object_type,
    proposal,
):
    """
    Build the attribute collection shown by the editor.

    Includes:

    - canonical attributes
    - proposed CREATE attributes

    Canonical database rows are never modified.
    """

    attributes = []

    canonical_attributes = _get_canonical_attributes(
        object_type,
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

        attributes.append(attribute)

    if proposal:

        create_changes = proposal.changes.filter(
            target_type="AttributeDefinition",
            operation=(ProposalChange.Operation.CREATE),
            parent_type="ObjectType",
            parent_id=object_type.id,
        ).order_by("created_at")

        for change in create_changes:

            if not change.target_id:
                continue

            if str(change.target_id) in canonical_ids:
                continue

            after = change.after or {}

            values = {
                "name": after.get(
                    "name",
                    "",
                ),
                "key": after.get(
                    "key",
                    "",
                ),
                "data_type": after.get(
                    "data_type",
                    AttributeDefinition.DataType.TEXT,
                ),
                "description": after.get(
                    "description",
                    "",
                ),
                "required": after.get(
                    "required",
                    False,
                ),
                "nullable": after.get(
                    "nullable",
                    False,
                ),
                "default_value": after.get(
                    "default_value",
                    None,
                ),
                "sort_order": after.get(
                    "sort_order",
                    0,
                ),
                "is_active": after.get(
                    "is_active",
                    True,
                ),
            }

            for update_change in _attribute_update_changes(
                change.target_id,
                proposal,
            ):
                update_after = update_change.after or {}

                field = update_after.get("field")

                if field in values and "value" in update_after:
                    values[field] = update_after["value"]

            proposed_fields = _attribute_proposed_fields(
                change.target_id,
                proposal,
            )

            attributes.append(
                type(
                    "ProposedAttribute",
                    (),
                    {
                        "id": change.target_id,
                        "proposed_values": values,
                        "proposed_fields": proposed_fields,
                        "attribute_proposed": True,
                        "attribute_created": True,
                        "data_type_choices": (AttributeDefinition.DataType.choices),
                    },
                )()
            )

    return attributes


# =====================================================================
# Validation / coercion
# =====================================================================


def _serialize_value(value):
    if isinstance(value, bool):
        return "true" if value else "false"

    if value is None:
        return ""

    return str(value)


def _coerce_boolean(
    value,
    label,
):
    normalised = str(value).strip().lower()

    if normalised in {
        "true",
        "1",
        "yes",
        "on",
    }:
        return True

    if normalised in {
        "false",
        "0",
        "no",
        "off",
    }:
        return False

    raise ValueError(f"{label} must be true or false.")


def _coerce_object_type_field(
    field,
    raw_value,
):
    if field in {
        "name",
        "key",
        "description",
    }:
        return raw_value.strip()

    if field == "is_active":
        return _coerce_boolean(
            raw_value,
            "Status",
        )

    if field == "sort_order":
        value = raw_value.strip()

        if not value:
            raise ValueError("Sort order is required.")

        try:
            value = int(value)
        except (TypeError, ValueError):
            raise ValueError("Sort order must be a whole number.")

        if value < 0:
            raise ValueError("Sort order cannot be negative.")

        return value

    raise ValueError("Unsupported field.")


def _validate_object_type_field(
    model,
    object_type,
    field,
    value,
):
    if field == "name":

        if not value:
            return "Name is required."

        if len(value) > 100:
            return "Name cannot exceed 100 characters."

        return None

    if field == "key":

        if not value:
            return "Key is required."

        if len(value) > 100:
            return "Key cannot exceed 100 characters."

        query = ObjectType.objects.filter(
            model=model,
            key=value,
        )

        if object_type:
            query = query.exclude(
                id=object_type.id,
            )

        if query.exists():
            return "An object type with this key " "already exists."

        return None

    if field in {
        "description",
        "sort_order",
        "is_active",
    }:
        return None

    return "Unsupported field."


def _coerce_default_value(
    data_type,
    raw_value,
):
    """
    Convert the text-box representation into a sensible JSON value.

    Text-like types remain strings.

    Number becomes int/float.

    Boolean becomes bool.

    Date/time remain ISO strings.

    Empty means no default.
    """

    raw_value = raw_value.strip()

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


def _coerce_attribute_data(
    request,
    existing_values,
):
    """
    Read the complete AttributeDefinition editor.
    """

    name = request.POST.get(
        "attribute_name",
        existing_values.get(
            "name",
            "",
        ),
    ).strip()

    key = request.POST.get(
        "attribute_key",
        existing_values.get(
            "key",
            "",
        ),
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
        existing_values.get(
            "description",
            "",
        ),
    ).strip()

    default_value_raw = request.POST.get(
        "attribute_default_value",
        "",
    )

    required = request.POST.get("attribute_required") == "on"

    nullable = request.POST.get("attribute_nullable") == "on"

    is_active = existing_values.get(
        "is_active",
        True,
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
        sort_order = int(sort_order_raw)

        if sort_order < 0:
            errors["sort_order"] = "Sort order cannot be negative."

    except (TypeError, ValueError):
        sort_order = 0
        errors["sort_order"] = "Sort order must be a whole number."

    values = {
        "name": name,
        "key": key,
        "data_type": data_type,
        "description": description,
        "required": required,
        "nullable": nullable,
        "default_value": default_value,
        "sort_order": sort_order,
        "is_active": is_active,
    }

    return values, errors


def _validate_attribute_key(
    object_type,
    attribute_id,
    key,
):
    if not key:
        return "Key is required."

    query = AttributeDefinition.objects.filter(
        object_type=object_type,
        key=key,
    )

    if attribute_id:
        query = query.exclude(
            id=attribute_id,
        )

    if query.exists():
        return "An attribute with this key " "already exists."

    return None


def _render_editor(
    request,
    context,
    object_type,
    proposal,
    effective_values,
    errors=None,
):
    context.update(
        {
            "object_type": object_type,
            "proposal": proposal,
            "proposed_values": effective_values,
            "proposed_fields": (
                _object_type_proposed_fields(
                    object_type,
                    proposal,
                )
                if object_type
                else {}
            ),
            "attributes": (
                _build_attribute_view_objects(
                    object_type,
                    proposal,
                )
                if object_type
                else []
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
        "model/object_type_editor.html",
        context,
    )


def _build_form(
    values,
    errors=None,
):
    errors = errors or {}

    return {
        "name": {
            "value": values.get(
                "name",
                "",
            ),
            "errors": errors.get("name"),
        },
        "key": {
            "value": values.get(
                "key",
                "",
            ),
            "errors": errors.get("key"),
        },
        "description": {
            "value": values.get(
                "description",
                "",
            ),
            "errors": errors.get("description"),
        },
        "is_active": {
            "value": values.get(
                "is_active",
                True,
            ),
            "errors": errors.get("is_active"),
        },
        "sort_order": {
            "value": values.get(
                "sort_order",
                0,
            ),
            "errors": errors.get("sort_order"),
        },
    }


# =====================================================================
# View
# =====================================================================


@login_required
def object_type_editor(
    request,
    model_id,
    object_type_id=None,
):
    context = get_model_context(
        request,
        model_id,
    )

    model = context["model"]

    proposal = context["my_working_proposal"]

    object_type = None

    if object_type_id:

        object_type = ObjectType.objects.filter(
            id=object_type_id,
            model=model,
        ).first()

        if object_type is None:
            raise Http404("Object type not found.")

    # =================================================================
    # ObjectType lifecycle
    # =================================================================

    if (
        request.method == "POST"
        and request.POST.get("action") == "set_object_type_status"
    ):

        if object_type is None:
            return JsonResponse(
                {
                    "success": False,
                    "error": ("Object type not found."),
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

        canonical_value = object_type.is_active

        if desired_active == canonical_value:

            if proposal:
                ProposalService.discard_change(
                    proposal=proposal,
                    target_type="ObjectType",
                    target_id=object_type.id,
                    field="is_active",
                )

            return JsonResponse(
                {
                    "success": True,
                    "value": _serialize_value(canonical_value),
                    "proposed": False,
                }
            )

        proposal = ProposalService.get_or_create_working(
            model=model,
            user=request.user,
        )

        ProposalService.record_change(
            proposal=proposal,
            operation=(ProposalChange.Operation.UPDATE),
            target_type="ObjectType",
            target_id=object_type.id,
            parent_type="Model",
            parent_id=model.id,
            field="is_active",
            before={
                "field": "is_active",
                "value": canonical_value,
            },
            after={
                "field": "is_active",
                "value": desired_active,
            },
        )

        return JsonResponse(
            {
                "success": True,
                "value": _serialize_value(desired_active),
                "proposed": True,
            }
        )

    # =================================================================
    # ObjectType lifecycle discard
    # =================================================================

    if (
        request.method == "POST"
        and request.POST.get("action") == "discard_object_type_status"
    ):

        if object_type is None:
            return JsonResponse(
                {
                    "success": False,
                    "error": ("Object type not found."),
                },
                status=404,
            )

        if proposal:
            ProposalService.discard_change(
                proposal=proposal,
                target_type="ObjectType",
                target_id=object_type.id,
                field="is_active",
            )

        return JsonResponse(
            {
                "success": True,
                "value": _serialize_value(object_type.is_active),
                "proposed": False,
            }
        )

    # =================================================================
    # Attribute lifecycle
    # =================================================================

    if (
        request.method == "POST"
        and request.POST.get("action") == "set_attribute_status"
    ):

        if object_type is None:
            return JsonResponse(
                {
                    "success": False,
                    "error": ("Object type not found."),
                },
                status=404,
            )

        attribute_id = request.POST.get("attribute_id")

        if not attribute_id:
            return JsonResponse(
                {
                    "success": False,
                    "error": ("Attribute ID is required."),
                },
                status=400,
            )

        try:
            attribute_uuid = uuid.UUID(attribute_id)
        except ValueError:
            return JsonResponse(
                {
                    "success": False,
                    "error": ("Invalid attribute ID."),
                },
                status=400,
            )

        (
            attribute,
            effective_values,
            attribute_created,
        ) = _attribute_proposal_values(
            attribute_uuid,
            object_type,
            proposal,
        )

        if effective_values is None:
            return JsonResponse(
                {
                    "success": False,
                    "error": ("Attribute not found."),
                },
                status=404,
            )

        desired_active = _coerce_boolean(
            request.POST.get(
                "is_active",
                "",
            ),
            "Status",
        )

        canonical_active = (
            effective_values["is_active"] if attribute_created else attribute.is_active
        )

        # For an existing attribute, compare
        # against canonical state so that reverting
        # to canonical removes the proposal.

        if not attribute_created:
            if desired_active == canonical_active:

                if proposal:
                    ProposalService.discard_change(
                        proposal=proposal,
                        target_type="AttributeDefinition",
                        target_id=attribute_uuid,
                        field="is_active",
                    )

                return JsonResponse(
                    {
                        "success": True,
                        "value": _serialize_value(canonical_active),
                        "proposed": (
                            _attribute_is_proposed(
                                attribute_uuid,
                                proposal,
                            )
                        ),
                    }
                )

        proposal = ProposalService.get_or_create_working(
            model=model,
            user=request.user,
        )

        before_value = (
            canonical_active if not attribute_created else effective_values["is_active"]
        )

        if desired_active == before_value:
            return JsonResponse(
                {
                    "success": True,
                    "value": _serialize_value(desired_active),
                    "proposed": True,
                }
            )

        ProposalService.record_change(
            proposal=proposal,
            operation=(ProposalChange.Operation.UPDATE),
            target_type="AttributeDefinition",
            target_id=attribute_uuid,
            parent_type="ObjectType",
            parent_id=object_type.id,
            field="is_active",
            before={
                "field": "is_active",
                "value": before_value,
            },
            after={
                "field": "is_active",
                "value": desired_active,
            },
        )

        return JsonResponse(
            {
                "success": True,
                "value": _serialize_value(desired_active),
                "proposed": True,
            }
        )

    # =================================================================
    # Create AttributeDefinition
    # =================================================================

    if request.method == "POST" and request.POST.get("action") == "create_attribute":

        if object_type is None:
            return JsonResponse(
                {
                    "success": False,
                    "error": ("Object type not found."),
                },
                status=404,
            )

        try:
            submitted_values, errors = _coerce_attribute_data(
                request,
                {
                    "name": "",
                    "key": "",
                    "data_type": (AttributeDefinition.DataType.TEXT),
                    "description": "",
                    "required": False,
                    "nullable": False,
                    "default_value": None,
                    "sort_order": 0,
                    "is_active": True,
                },
            )
        except ValueError as exc:
            return JsonResponse(
                {
                    "success": False,
                    "error": str(exc),
                },
                status=400,
            )

        key_error = _validate_attribute_key(
            object_type=object_type,
            attribute_id=None,
            key=submitted_values["key"],
        )

        if key_error:
            errors["key"] = key_error

        if errors:
            return JsonResponse(
                {
                    "success": False,
                    "errors": errors,
                    "error": ("Please correct the " "attribute before adding it."),
                },
                status=400,
            )

        proposal = ProposalService.get_or_create_working(
            model=model,
            user=request.user,
        )

        attribute_uuid = uuid.uuid4()

        ProposalService.record_change(
            proposal=proposal,
            operation=(ProposalChange.Operation.CREATE),
            target_type="AttributeDefinition",
            target_id=attribute_uuid,
            parent_type="ObjectType",
            parent_id=object_type.id,
            before=None,
            after=submitted_values,
        )

        return JsonResponse(
            {
                "success": True,
                "created": True,
                "attribute_id": str(attribute_uuid),
                "values": {
                    field: _serialize_value(submitted_values[field])
                    for field in ATTRIBUTE_FIELDS
                },
                "proposed": True,
                "proposed_fields": {field: True for field in ATTRIBUTE_FIELDS},
            }
        )

    # =================================================================
    # Save AttributeDefinition
    # =================================================================

    if request.method == "POST" and request.POST.get("action") == "save_attribute":

        if object_type is None:
            return JsonResponse(
                {
                    "success": False,
                    "error": ("Object type not found."),
                },
                status=404,
            )

        attribute_id = request.POST.get("attribute_id")

        if not attribute_id:
            return JsonResponse(
                {
                    "success": False,
                    "error": ("Attribute ID is required."),
                },
                status=400,
            )

        try:
            attribute_uuid = uuid.UUID(attribute_id)
        except ValueError:
            return JsonResponse(
                {
                    "success": False,
                    "error": ("Invalid attribute ID."),
                },
                status=400,
            )

        (
            attribute,
            effective_values,
            attribute_created,
        ) = _attribute_proposal_values(
            attribute_uuid,
            object_type,
            proposal,
        )

        if effective_values is None:
            return JsonResponse(
                {
                    "success": False,
                    "error": ("Attribute not found."),
                },
                status=404,
            )

        submitted_values, errors = _coerce_attribute_data(
            request,
            effective_values,
        )

        if errors:
            return JsonResponse(
                {
                    "success": False,
                    "errors": errors,
                    "error": ("Please correct the " "attribute before saving."),
                },
                status=400,
            )

        key_error = _validate_attribute_key(
            object_type=object_type,
            attribute_id=(None if attribute_created else attribute_uuid),
            key=submitted_values["key"],
        )

        if key_error:
            errors["key"] = key_error

        if errors:
            return JsonResponse(
                {
                    "success": False,
                    "errors": errors,
                    "error": ("Please correct the " "attribute before saving."),
                },
                status=400,
            )

        proposal = ProposalService.get_or_create_working(
            model=model,
            user=request.user,
        )

        # -------------------------------------------------------------
        # CREATE attributes
        # -------------------------------------------------------------

        if attribute_created:

            create_change = _attribute_create_change(
                attribute_uuid,
                proposal,
            )

            if create_change is None:
                return JsonResponse(
                    {
                        "success": False,
                        "error": ("Proposed attribute not found."),
                    },
                    status=404,
                )

            create_after = dict(create_change.after or {})

            # Keep the CREATE as the base state.
            # Only create UPDATE changes for fields that differ
            # from that base state.

            for field in ATTRIBUTE_FIELDS:

                base_value = create_after.get(field)

                submitted_value = submitted_values[field]

                existing_update = next(
                    (
                        change
                        for change in proposal.changes.filter(
                            target_type="AttributeDefinition",
                            target_id=attribute_uuid,
                            operation=ProposalChange.Operation.UPDATE,
                            after__field=field,
                        )
                    ),
                    None,
                )

                if submitted_value == base_value:

                    if existing_update:
                        ProposalService.discard_change(
                            proposal=proposal,
                            target_type="AttributeDefinition",
                            target_id=attribute_uuid,
                            field=field,
                        )

                    continue

                ProposalService.record_change(
                    proposal=proposal,
                    operation=(ProposalChange.Operation.UPDATE),
                    target_type="AttributeDefinition",
                    target_id=attribute_uuid,
                    parent_type="ObjectType",
                    parent_id=object_type.id,
                    field=field,
                    before={
                        "field": field,
                        "value": base_value,
                    },
                    after={
                        "field": field,
                        "value": submitted_value,
                    },
                )

        # -------------------------------------------------------------
        # Existing canonical attribute
        # -------------------------------------------------------------

        else:

            canonical_values = _attribute_canonical_values(
                attribute,
            )

            for field in ATTRIBUTE_FIELDS:

                canonical_value = canonical_values[field]

                submitted_value = submitted_values[field]

                if submitted_value == canonical_value:

                    if proposal:
                        ProposalService.discard_change(
                            proposal=proposal,
                            target_type="AttributeDefinition",
                            target_id=attribute_uuid,
                            field=field,
                        )

                    continue

                ProposalService.record_change(
                    proposal=proposal,
                    operation=(ProposalChange.Operation.UPDATE),
                    target_type="AttributeDefinition",
                    target_id=attribute_uuid,
                    parent_type="ObjectType",
                    parent_id=object_type.id,
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

        _, effective_values, attribute_created = _attribute_proposal_values(
            attribute_uuid,
            object_type,
            proposal,
        )

        return JsonResponse(
            {
                "success": True,
                "attribute_id": str(attribute_uuid),
                "values": {
                    field: _serialize_value(effective_values[field])
                    for field in ATTRIBUTE_FIELDS
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

        if object_type is None:
            return JsonResponse(
                {
                    "success": False,
                    "error": ("Object type not found."),
                },
                status=404,
            )

        attribute_id = request.POST.get("attribute_id")

        if not attribute_id:
            return JsonResponse(
                {
                    "success": False,
                    "error": ("Attribute ID is required."),
                },
                status=400,
            )

        try:
            attribute_uuid = uuid.UUID(attribute_id)
        except ValueError:
            return JsonResponse(
                {
                    "success": False,
                    "error": ("Invalid attribute ID."),
                },
                status=400,
            )

        if proposal is None:
            return JsonResponse(
                {
                    "success": False,
                    "error": ("There is no working " "proposal to discard."),
                },
                status=400,
            )

        (
            attribute,
            effective_values,
            attribute_created,
        ) = _attribute_proposal_values(
            attribute_uuid,
            object_type,
            proposal,
        )

        if effective_values is None:
            return JsonResponse(
                {
                    "success": False,
                    "error": ("Attribute not found."),
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
                    "attribute_id": str(attribute_uuid),
                }
            )

        canonical_values = _attribute_canonical_values(attribute)

        return JsonResponse(
            {
                "success": True,
                "removed": False,
                "attribute_id": str(attribute_uuid),
                "values": {
                    field: _serialize_value(canonical_values[field])
                    for field in ATTRIBUTE_FIELDS
                },
                "proposed": False,
                "proposed_fields": {field: False for field in ATTRIBUTE_FIELDS},
            }
        )

    # =================================================================
    # ObjectType field editor
    # =================================================================

    if request.method == "POST" and request.POST.get("field"):

        if object_type is None:
            return JsonResponse(
                {
                    "success": False,
                    "error": (
                        "Field-level editing is only "
                        "available for an existing "
                        "object type."
                    ),
                },
                status=400,
            )

        field = request.POST.get(
            "field",
            "",
        ).strip()

        if field not in OBJECT_TYPE_FIELDS:
            return JsonResponse(
                {
                    "success": False,
                    "error": ("Unsupported field."),
                },
                status=400,
            )

        action = request.POST.get(
            "action",
            "",
        ).strip()

        # -------------------------------------------------------------
        # Discard field
        # -------------------------------------------------------------

        if action == "discard":

            if proposal:
                ProposalService.discard_change(
                    proposal=proposal,
                    target_type="ObjectType",
                    target_id=object_type.id,
                    field=field,
                )

            canonical_values = _object_type_canonical_values(
                object_type,
            )

            return JsonResponse(
                {
                    "success": True,
                    "value": _serialize_value(canonical_values[field]),
                    "proposed": False,
                }
            )

        if action:
            return JsonResponse(
                {
                    "success": False,
                    "error": ("Invalid action."),
                },
                status=400,
            )

        raw_value = request.POST.get(
            "value",
            "",
        )

        try:
            value = _coerce_object_type_field(
                field,
                raw_value,
            )
        except ValueError as exc:
            return JsonResponse(
                {
                    "success": False,
                    "error": str(exc),
                },
                status=400,
            )

        validation_error = _validate_object_type_field(
            model=model,
            object_type=object_type,
            field=field,
            value=value,
        )

        if validation_error:
            return JsonResponse(
                {
                    "success": False,
                    "error": validation_error,
                },
                status=400,
            )

        canonical_values = _object_type_canonical_values(
            object_type,
        )

        canonical_value = canonical_values[field]

        if value == canonical_value:

            if proposal:
                ProposalService.discard_change(
                    proposal=proposal,
                    target_type="ObjectType",
                    target_id=object_type.id,
                    field=field,
                )

            return JsonResponse(
                {
                    "success": True,
                    "value": _serialize_value(canonical_value),
                    "proposed": False,
                }
            )

        proposal = ProposalService.get_or_create_working(
            model=model,
            user=request.user,
        )

        ProposalService.record_change(
            proposal=proposal,
            operation=(ProposalChange.Operation.UPDATE),
            target_type="ObjectType",
            target_id=object_type.id,
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
    # Create ObjectType
    # =================================================================

    if request.method == "POST" and object_type is None:

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

        if ObjectType.objects.filter(
            model=model,
            key=key,
        ).exists():
            errors["key"] = "An object type with this key " "already exists."

        if errors:

            effective_values = {
                "name": name,
                "key": key,
                "description": description,
                "sort_order": 0,
                "is_active": True,
            }

            return _render_editor(
                request=request,
                context=context,
                object_type=None,
                proposal=proposal,
                effective_values=effective_values,
                errors=errors,
            )

        proposal = ProposalService.get_or_create_working(
            model=model,
            user=request.user,
        )

        object_type_uuid = uuid.uuid4()

        ProposalService.record_change(
            proposal=proposal,
            operation=(ProposalChange.Operation.CREATE),
            target_type="ObjectType",
            target_id=object_type_uuid,
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
            "model:object_types",
            model.id,
        )

    # =================================================================
    # GET
    # =================================================================

    if object_type:
        effective_values = _object_type_effective_values(
            object_type,
            proposal,
        )

    else:
        effective_values = {
            "name": "",
            "key": "",
            "description": "",
            "sort_order": 0,
            "is_active": True,
        }

    return _render_editor(
        request=request,
        context=context,
        object_type=object_type,
        proposal=proposal,
        effective_values=effective_values,
    )
