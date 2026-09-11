import uuid
from types import SimpleNamespace

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render

from model.models.attribute_definition import AttributeDefinition
from model.models.object_type import ObjectType
from model.models.proposal import ProposalChange
from model.services.proposal.proposal import ProposalService
from model.views.common_context import get_model_context

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
# ObjectType helpers
# =====================================================================


def _object_type_canonical_values(object_type):
    return {
        "name": object_type.name,
        "key": object_type.key,
        "description": object_type.description,
        "sort_order": object_type.sort_order,
        "is_active": object_type.is_active,
    }


def _object_type_create_change(
    object_type_id,
    proposal,
):
    if not proposal:
        return None

    return (
        proposal.changes.filter(
            target_type="ObjectType",
            target_id=object_type_id,
            operation=ProposalChange.Operation.CREATE,
        )
        .order_by("created_at")
        .first()
    )


def _object_type_is_proposed_only(
    object_type_id,
    proposal,
):
    """
    True when the ObjectType exists only as a CREATE proposal and does
    not yet exist canonically.
    """
    return (
        proposal is not None
        and _object_type_create_change(
            object_type_id,
            proposal,
        )
        is not None
        and not ObjectType.objects.filter(
            id=object_type_id,
        ).exists()
    )


def _object_type_effective_values(
    object_type,
    proposal,
):
    """
    Resolve the effective ObjectType state.

    Supports both canonical ObjectTypes and proposal-only CREATE
    ObjectTypes.
    """

    if object_type is not None:
        values = _object_type_canonical_values(
            object_type,
        )
    else:
        raise ValueError("A canonical ObjectType is required.")

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


def _proposed_only_object_type(
    object_type_id,
    proposal,
):
    """
    Construct a lightweight ObjectType-like object from a CREATE
    proposal.

    It is intentionally not written to the database.
    """

    change = _object_type_create_change(
        object_type_id,
        proposal,
    )

    if change is None:
        return None

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
        "description": after.get(
            "description",
            "",
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

    # Apply subsequent UPDATE changes if any already exist.
    changes = proposal.changes.filter(
        target_type="ObjectType",
        target_id=object_type_id,
        operation=ProposalChange.Operation.UPDATE,
    ).order_by("created_at")

    for update in changes:
        update_after = update.after or {}
        field = update_after.get("field")

        if field in values and "value" in update_after:
            values[field] = update_after["value"]

    return SimpleNamespace(
        id=object_type_id,
        model_id=change.parent_id,
        **values,
    )


def _object_type_proposed_fields(
    object_type_id,
    proposal,
):
    result = {field: False for field in OBJECT_TYPE_FIELDS}

    if not proposal:
        return result

    create_change = _object_type_create_change(
        object_type_id,
        proposal,
    )

    if create_change:
        for field in result:
            result[field] = True

    changes = proposal.changes.filter(
        target_type="ObjectType",
        target_id=object_type_id,
        operation=ProposalChange.Operation.UPDATE,
    )

    for change in changes:
        after = change.after or {}
        field = after.get("field")

        if field in result:
            result[field] = True

    return result


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
    Resolve either a canonical AttributeDefinition or a proposed-only
    CREATE attribute.
    """

    attribute = AttributeDefinition.objects.filter(
        id=attribute_id,
        object_type=object_type if isinstance(object_type, ObjectType) else None,
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
    )

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


def _build_attribute_view_objects(
    object_type,
    proposal,
):
    """
    Build the working attribute collection.

    For a canonical ObjectType this combines canonical attributes with
    proposed creates.

    For a proposal-only ObjectType there are no canonical attributes,
    so only proposed CREATE attributes are returned.
    """

    attributes = []

    canonical_attributes = []

    if isinstance(
        object_type,
        ObjectType,
    ):
        canonical_attributes = list(
            AttributeDefinition.objects.filter(
                object_type=object_type,
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

        attributes.append(attribute)

    if proposal and object_type:

        object_type_id = object_type.id

        create_changes = proposal.changes.filter(
            target_type="AttributeDefinition",
            operation=(ProposalChange.Operation.CREATE),
            parent_type="ObjectType",
            parent_id=object_type_id,
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
                SimpleNamespace(
                    id=change.target_id,
                    proposed_values=values,
                    proposed_fields=proposed_fields,
                    attribute_proposed=True,
                    attribute_created=True,
                    data_type_choices=(AttributeDefinition.DataType.choices),
                )
            )

    return attributes


# =====================================================================
# Value conversion
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
    value = str(value).strip().lower()

    if value in {
        "true",
        "1",
        "yes",
        "on",
    }:
        return True

    if value in {
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
        except ValueError:
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

    elif field == "key":

        if not value:
            return "Key is required."

        if len(value) > 100:
            return "Key cannot exceed 100 characters."

        query = ObjectType.objects.filter(
            model=model,
            key=value,
        )

        if isinstance(
            object_type,
            ObjectType,
        ):
            query = query.exclude(
                id=object_type.id,
            )

        if query.exists():
            return "An object type with this key " "already exists."

    elif field in {
        "description",
        "sort_order",
        "is_active",
    }:
        pass

    else:
        return "Unsupported field."

    return None


def _coerce_default_value(
    data_type,
    raw_value,
):
    raw_value = (raw_value or "").strip()

    if raw_value == "":
        return None

    if data_type == (AttributeDefinition.DataType.NUMBER):
        try:
            if "." in raw_value:
                return float(raw_value)

            return int(raw_value)

        except ValueError:
            raise ValueError("Default value must be a number.")

    if data_type == (AttributeDefinition.DataType.BOOLEAN):
        return _coerce_boolean(
            raw_value,
            "Default value",
        )

    return raw_value


def _coerce_attribute_data(
    request,
    existing_values,
):
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
                    object_type.id,
                    proposal,
                )
                if object_type is not None
                else {field: False for field in OBJECT_TYPE_FIELDS}
            ),
            "attributes": (
                _build_attribute_view_objects(
                    object_type,
                    proposal,
                )
                if object_type is not None
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


# =====================================================================
# Main view
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
    proposal_only = False

    if object_type_id:

        object_type = ObjectType.objects.filter(
            id=object_type_id,
            model=model,
        ).first()

        if object_type is None:

            object_type = _proposed_only_object_type(
                object_type_id,
                proposal,
            )

            if object_type is None:
                raise Http404("Object type not found.")

            proposal_only = True

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

        desired_active = _coerce_boolean(
            request.POST.get(
                "is_active",
                "",
            ),
            "Status",
        )

        # -------------------------------------------------------------
        # Proposal-only CREATE
        #
        # Update the CREATE payload itself.
        # -------------------------------------------------------------

        if proposal_only:

            create_change = _object_type_create_change(
                object_type.id,
                proposal,
            )

            if create_change is None:
                return JsonResponse(
                    {
                        "success": False,
                        "error": ("Proposed object type not found."),
                    },
                    status=404,
                )

            after = dict(create_change.after or {})

            after["is_active"] = desired_active

            create_change.after = after
            create_change.save(
                update_fields=[
                    "after",
                    "updated_at",
                ]
            )

            ProposalService.reset_validation(proposal)

            return JsonResponse(
                {
                    "success": True,
                    "value": _serialize_value(desired_active),
                    "proposed": True,
                }
            )

        canonical_active = object_type.is_active

        if desired_active == canonical_active:

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
                    "value": _serialize_value(canonical_active),
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

        if proposal_only:

            create_change = _object_type_create_change(
                object_type.id,
                proposal,
            )

            if create_change is None:
                return JsonResponse(
                    {
                        "success": False,
                        "error": ("Proposed object type not found."),
                    },
                    status=404,
                )

            return JsonResponse(
                {
                    "success": True,
                    "value": _serialize_value(
                        (create_change.after or {}).get(
                            "is_active",
                            True,
                        )
                    ),
                    "proposed": True,
                }
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
            (
                object_type
                if isinstance(
                    object_type,
                    ObjectType,
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

        desired_active = _coerce_boolean(
            request.POST.get(
                "is_active",
                "",
            ),
            "Status",
        )

        # A proposed CREATE attribute has no canonical row.
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

            after = dict(create_change.after or {})

            after["is_active"] = desired_active

            create_change.after = after

            create_change.save(
                update_fields=[
                    "after",
                    "updated_at",
                ]
            )

            ProposalService.reset_validation(proposal)

            return JsonResponse(
                {
                    "success": True,
                    "value": _serialize_value(desired_active),
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
                    "proposed_fields": (
                        _attribute_proposed_fields(
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
                "value": _serialize_value(desired_active),
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

        if isinstance(
            object_type,
            ObjectType,
        ):

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
                    "error": ("Please correct the attribute " "before adding it."),
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
            after={
                **submitted_values,
                "is_active": True,
            },
        )

        return JsonResponse(
            {
                "success": True,
                "created": True,
                "attribute_id": str(attribute_uuid),
                "values": {
                    field: _serialize_value(
                        (
                            {
                                **submitted_values,
                                "is_active": True,
                            }
                        )[field]
                    )
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
            (
                object_type
                if isinstance(
                    object_type,
                    ObjectType,
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

        if isinstance(
            object_type,
            ObjectType,
        ):

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
        # Proposed new AttributeDefinition.
        #
        # Update the CREATE payload.
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

            create_after.update(submitted_values)

            create_after.setdefault(
                "is_active",
                True,
            )

            create_change.after = create_after

            create_change.save(
                update_fields=[
                    "after",
                    "updated_at",
                ]
            )

            ProposalService.reset_validation(proposal)

        # -------------------------------------------------------------
        # Existing canonical attribute.
        # -------------------------------------------------------------

        else:

            canonical_values = _attribute_canonical_values(attribute)

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

        (
            _,
            effective_values,
            attribute_created,
        ) = _attribute_proposal_values(
            attribute_uuid,
            (
                object_type
                if isinstance(
                    object_type,
                    ObjectType,
                )
                else None
            ),
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
                "proposed": True,
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
            (
                object_type
                if isinstance(
                    object_type,
                    ObjectType,
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
    # ObjectType field editing
    # =================================================================

    if request.method == "POST" and request.POST.get("field"):

        if object_type is None:
            return JsonResponse(
                {
                    "success": False,
                    "error": ("Object type not found."),
                },
                status=404,
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
        # Discard
        # -------------------------------------------------------------

        if action == "discard":

            if proposal is None:
                return JsonResponse(
                    {
                        "success": False,
                        "error": ("There is no working " "proposal to discard."),
                    },
                    status=400,
                )

            if proposal_only:

                create_change = _object_type_create_change(
                    object_type.id,
                    proposal,
                )

                if create_change is None:
                    return JsonResponse(
                        {
                            "success": False,
                            "error": ("Proposed object type " "not found."),
                        },
                        status=404,
                    )

                after = create_change.after or {}

                # For a CREATE proposal, field-level
                # discard means restore the original
                # CREATE value. The original CREATE
                # payload is itself the working baseline.
                #
                # The editor therefore does not currently
                # maintain an independent baseline. A full
                # proposal discard remains available from
                # the index.

                return JsonResponse(
                    {
                        "success": True,
                        "value": _serialize_value(
                            after.get(
                                field,
                                "",
                            )
                        ),
                        "proposed": True,
                    }
                )

            ProposalService.discard_change(
                proposal=proposal,
                target_type="ObjectType",
                target_id=object_type.id,
                field=field,
            )

            canonical_values = _object_type_canonical_values(object_type)

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
                    "error": "Invalid action.",
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
            model,
            object_type,
            field,
            value,
        )

        if validation_error:
            return JsonResponse(
                {
                    "success": False,
                    "error": validation_error,
                },
                status=400,
            )

        # -------------------------------------------------------------
        # Proposal-only ObjectType.
        #
        # Update its CREATE payload.
        # -------------------------------------------------------------

        if proposal_only:

            create_change = _object_type_create_change(
                object_type.id,
                proposal,
            )

            if create_change is None:
                return JsonResponse(
                    {
                        "success": False,
                        "error": ("Proposed object type " "not found."),
                    },
                    status=404,
                )

            after = dict(create_change.after or {})

            after[field] = value

            create_change.after = after

            create_change.save(
                update_fields=[
                    "after",
                    "updated_at",
                ]
            )

            ProposalService.reset_validation(proposal)

            return JsonResponse(
                {
                    "success": True,
                    "value": _serialize_value(value),
                    "proposed": True,
                }
            )

        # -------------------------------------------------------------
        # Existing canonical ObjectType.
        # -------------------------------------------------------------

        canonical_values = _object_type_canonical_values(object_type)

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
                model=model,
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

        # -------------------------------------------------------------
        # Important:
        #
        # Go directly to the proposed ObjectType editor so the user
        # can continue building the same working proposal, including
        # attributes.
        # -------------------------------------------------------------

        return redirect(
            "model:object_type_edit",
            model.id,
            object_type_uuid,
        )

    # =================================================================
    # GET
    # =================================================================

    if object_type is not None:

        if proposal_only:

            effective_values = {
                "name": object_type.name,
                "key": object_type.key,
                "description": object_type.description,
                "sort_order": object_type.sort_order,
                "is_active": object_type.is_active,
            }

        else:

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
