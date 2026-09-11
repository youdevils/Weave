import uuid
from types import SimpleNamespace

from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render

from model.models.attribute_definition import AttributeDefinition
from model.models.object_type import ObjectType
from model.models.proposal import ProposalChange
from model.services.proposal.proposal import ProposalService
from model.views.common_context import get_model_context

EDITABLE_FIELDS = {
    "name",
    "key",
    "description",
    "is_active",
    "sort_order",
}


ATTRIBUTE_EDITABLE_FIELDS = {
    "name",
    "key",
    "data_type",
    "description",
    "required",
    "default_value",
    "sort_order",
}


# =====================================================================
# ObjectType helpers
# =====================================================================


def _canonical_values(object_type):
    return {
        "name": object_type.name,
        "key": object_type.key,
        "description": object_type.description,
        "is_active": object_type.is_active,
        "sort_order": object_type.sort_order,
    }


def _effective_values(object_type, proposal):
    """
    Canonical ObjectType values overlaid with current proposal values.
    """
    values = _canonical_values(object_type)

    if not proposal:
        return values

    changes = proposal.changes.filter(
        target_type="ObjectType",
        target_id=object_type.id,
        operation=ProposalChange.Operation.UPDATE,
    )

    for change in changes:
        after = change.after or {}
        field = after.get("field")

        if field in values and "value" in after:
            values[field] = after["value"]

    return values


def _proposed_fields(object_type, proposal):
    result = {field: False for field in EDITABLE_FIELDS}

    if not object_type or not proposal:
        return result

    changes = proposal.changes.filter(
        target_type="ObjectType",
        target_id=object_type.id,
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
        "default_value": attribute.default_value,
        "sort_order": attribute.sort_order,
    }


def _attribute_proposal_changes(
    attribute_id,
    proposal,
):
    if not proposal:
        return proposal.changes.none()

    return proposal.changes.filter(
        target_type="AttributeDefinition",
        target_id=attribute_id,
    )


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


def _attribute_effective_values(
    attribute,
    proposal,
):
    """
    Return canonical + proposed values for an existing attribute.
    """
    values = _attribute_canonical_values(attribute)

    if not proposal:
        return values

    changes = _attribute_proposal_changes(
        attribute.id,
        proposal,
    )

    for change in changes:
        after = change.after or {}
        field = after.get("field")

        if field in values and "value" in after:
            values[field] = after["value"]

    return values


def _proposed_attribute_values(
    attribute_id,
    object_type,
    proposal,
):
    """
    Resolve an AttributeDefinition's effective state.

    Supports both:

    1. Canonical attributes.
    2. Newly-created attributes that exist only in the working proposal.
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
        "name": after.get("name", ""),
        "key": after.get("key", ""),
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
        "default_value": after.get(
            "default_value",
            None,
        ),
        "sort_order": after.get(
            "sort_order",
            0,
        ),
    }

    # Overlay any later field-level updates to the proposed new object.
    changes = _attribute_proposal_changes(
        attribute_id,
        proposal,
    )

    for change in changes:
        if change.operation != ProposalChange.Operation.UPDATE:
            continue

        after = change.after or {}
        field = after.get("field")

        if field in values and "value" in after:
            values[field] = after["value"]

    return None, values, True


def _attribute_proposed_fields(
    attribute_id,
    proposal,
):
    result = {field: False for field in ATTRIBUTE_EDITABLE_FIELDS}

    if not proposal:
        return result

    changes = proposal.changes.filter(
        target_type="AttributeDefinition",
        target_id=attribute_id,
    )

    for change in changes:
        after = change.after or {}
        field = after.get("field")

        if field in result:
            result[field] = True

    create_change = _attribute_create_change(
        attribute_id,
        proposal,
    )

    if create_change:
        # A CREATE is itself a proposed attribute.
        # Individual field flags are not necessary for the UI,
        # but we return them as true so the state is explicit.
        for field in result:
            result[field] = True

    return result


def _get_attributes(object_type):
    if not object_type:
        return []

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
    Build the list displayed by the ObjectType editor.

    This combines:

        canonical AttributeDefinitions
        +
        proposed CREATE AttributeDefinitions

    without modifying canonical data.
    """

    attributes = []

    canonical_attributes = _get_attributes(
        object_type,
    )

    canonical_ids = set()

    for attribute in canonical_attributes:

        canonical_ids.add(str(attribute.id))

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

    # -------------------------------------------------------------
    # Proposed new attributes
    # -------------------------------------------------------------

    if proposal:

        create_changes = proposal.changes.filter(
            target_type="AttributeDefinition",
            operation=ProposalChange.Operation.CREATE,
            parent_type="ObjectType",
            parent_id=object_type.id,
        ).order_by("created_at")

        for change in create_changes:

            if not change.target_id:
                continue

            if str(change.target_id) in canonical_ids:
                continue

            after = change.after or {}

            attribute = SimpleNamespace(
                id=change.target_id,
                proposed_values={
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
                    "default_value": after.get(
                        "default_value",
                        None,
                    ),
                    "sort_order": after.get(
                        "sort_order",
                        0,
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

            # Overlay subsequent UPDATE changes.
            update_changes = proposal.changes.filter(
                target_type="AttributeDefinition",
                target_id=change.target_id,
                operation=ProposalChange.Operation.UPDATE,
            ).order_by("created_at")

            for update_change in update_changes:
                after_update = update_change.after or {}
                field = after_update.get("field")

                if field in attribute.proposed_values and "value" in after_update:
                    attribute.proposed_values[field] = after_update["value"]

            attributes.append(attribute)

    return attributes


# =====================================================================
# General helpers
# =====================================================================


def _build_form(
    effective_values,
    errors=None,
):
    errors = errors or {}

    return {
        "name": {
            "value": effective_values.get(
                "name",
                "",
            ),
            "errors": errors.get("name"),
        },
        "key": {
            "value": effective_values.get(
                "key",
                "",
            ),
            "errors": errors.get("key"),
        },
        "description": {
            "value": effective_values.get(
                "description",
                "",
            ),
            "errors": errors.get("description"),
        },
        "is_active": {
            "value": effective_values.get(
                "is_active",
                True,
            ),
            "errors": errors.get("is_active"),
        },
        "sort_order": {
            "value": effective_values.get(
                "sort_order",
                0,
            ),
            "errors": errors.get("sort_order"),
        },
    }


def _serialize_value(value):
    if isinstance(value, bool):
        return "true" if value else "false"

    if value is None:
        return ""

    return str(value)


def _coerce_field_value(
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
        value = raw_value.strip().lower()

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

        raise ValueError("Status must be active or inactive.")

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


def _validate_field(
    *,
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

        duplicate_query = ObjectType.objects.filter(
            model=model,
            key=value,
        )

        if object_type:
            duplicate_query = duplicate_query.exclude(
                id=object_type.id,
            )

        if duplicate_query.exists():
            return "An object type with this key " "already exists."

        return None

    if field in {
        "description",
        "is_active",
        "sort_order",
    }:
        return None

    return "Unsupported field."


def _coerce_attribute_data(
    request,
    existing_values,
):
    """
    Read the entire attribute editor.

    existing_values is the current effective working state, so the
    editor remains correct when an attribute is already proposed.
    """

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
        existing_values.get(
            "description",
            "",
        ),
    ).strip()

    default_value_raw = request.POST.get(
        "attribute_default_value",
        "",
    ).strip()

    required = (
        request.POST.get(
            "attribute_required",
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

    valid_data_types = {
        choice for choice, _label in AttributeDefinition.DataType.choices
    }

    if data_type not in valid_data_types:
        errors["data_type"] = "Invalid attribute data type."

    try:
        sort_order = int(sort_order_raw)

        if sort_order < 0:
            errors["sort_order"] = "Sort order cannot be negative."

    except (TypeError, ValueError):
        sort_order = 0
        errors["sort_order"] = "Sort order must be a whole number."

    if default_value_raw == "":
        default_value = None
    else:
        default_value = default_value_raw

    values = {
        "name": name,
        "key": key,
        "data_type": data_type,
        "description": description,
        "required": required,
        "default_value": default_value,
        "sort_order": sort_order,
    }

    return values, errors


def _validate_attribute_key(
    *,
    object_type,
    attribute_id,
    key,
):
    if not key:
        return "Key is required."

    duplicate_query = AttributeDefinition.objects.filter(
        object_type=object_type,
        key=key,
    )

    if attribute_id:
        duplicate_query = duplicate_query.exclude(
            id=attribute_id,
        )

    if duplicate_query.exists():
        return "An attribute with this key already exists."

    return None


def _render_editor(
    *,
    request,
    context,
    model,
    object_type,
    proposal,
    effective_values,
    errors=None,
):
    attributes = _build_attribute_view_objects(
        object_type,
        proposal,
    )

    context.update(
        {
            "object_type": object_type,
            "proposal": proposal,
            "proposed_values": effective_values,
            "proposed_fields": _proposed_fields(
                object_type,
                proposal,
            ),
            "attributes": attributes,
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
    # ADD ATTRIBUTE
    # =================================================================

    if request.method == "POST" and request.POST.get("action") == "create_attribute":
        if object_type is None:
            return JsonResponse(
                {
                    "success": False,
                    "error": ("An object type is required."),
                },
                status=400,
            )

        proposal = ProposalService.get_or_create_working(
            model=model,
            user=request.user,
        )

        name = request.POST.get(
            "attribute_name",
            "",
        ).strip()

        key = request.POST.get(
            "attribute_key",
            "",
        ).strip()

        data_type = request.POST.get(
            "attribute_data_type",
            AttributeDefinition.DataType.TEXT,
        ).strip()

        description = request.POST.get(
            "attribute_description",
            "",
        ).strip()

        default_value_raw = request.POST.get(
            "attribute_default_value",
            "",
        ).strip()

        required = (
            request.POST.get(
                "attribute_required",
            )
            == "on"
        )

        sort_order_raw = request.POST.get(
            "attribute_sort_order",
            "0",
        ).strip()

        errors = {}

        if not name:
            errors["name"] = "Name is required."

        elif len(name) > 100:
            errors["name"] = "Name cannot exceed 100 characters."

        key_error = _validate_attribute_key(
            object_type=object_type,
            attribute_id=None,
            key=key,
        )

        if key_error:
            errors["key"] = key_error

        valid_data_types = {
            choice for choice, _label in AttributeDefinition.DataType.choices
        }

        if data_type not in valid_data_types:
            errors["data_type"] = "Invalid attribute data type."

        try:
            sort_order = int(sort_order_raw)

            if sort_order < 0:
                errors["sort_order"] = "Sort order cannot be negative."

        except (TypeError, ValueError):
            sort_order = 0
            errors["sort_order"] = "Sort order must be a whole number."

        default_value = None if default_value_raw == "" else default_value_raw

        if errors:
            return JsonResponse(
                {
                    "success": False,
                    "errors": errors,
                    "error": ("Please correct the attribute " "before adding it."),
                },
                status=400,
            )

        attribute_id = uuid.uuid4()

        ProposalService.record_change(
            proposal=proposal,
            operation=ProposalChange.Operation.CREATE,
            target_type="AttributeDefinition",
            target_id=attribute_id,
            parent_type="ObjectType",
            parent_id=object_type.id,
            before=None,
            after={
                "name": name,
                "key": key,
                "data_type": data_type,
                "description": description,
                "required": required,
                "default_value": default_value,
                "sort_order": sort_order,
            },
        )

        return JsonResponse(
            {
                "success": True,
                "attribute_id": str(
                    attribute_id,
                ),
                "created": True,
                "values": {
                    "name": name,
                    "key": key,
                    "data_type": data_type,
                    "description": description,
                    "required": ("true" if required else "false"),
                    "default_value": (
                        "" if default_value is None else str(default_value)
                    ),
                    "sort_order": str(
                        sort_order,
                    ),
                },
            }
        )

    # =================================================================
    # SAVE ATTRIBUTE
    # =================================================================

    if request.method == "POST" and request.POST.get("action") == "save_attribute":
        if object_type is None:
            return JsonResponse(
                {
                    "success": False,
                    "error": ("An object type is required."),
                },
                status=400,
            )

        attribute_id = request.POST.get(
            "attribute_id",
        )

        if not attribute_id:
            return JsonResponse(
                {
                    "success": False,
                    "error": ("Attribute ID is required."),
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
                    "error": ("Invalid attribute ID."),
                },
                status=400,
            )

        attribute, existing_values, attribute_created = _proposed_attribute_values(
            attribute_uuid,
            object_type,
            proposal,
        )

        if existing_values is None:
            return JsonResponse(
                {
                    "success": False,
                    "error": "Attribute not found.",
                },
                status=404,
            )

        submitted_values, errors = _coerce_attribute_data(
            request,
            existing_values,
        )

        if errors:
            return JsonResponse(
                {
                    "success": False,
                    "errors": errors,
                    "error": ("Please correct the attribute " "before saving."),
                },
                status=400,
            )

        key_error = _validate_attribute_key(
            object_type=object_type,
            attribute_id=(None if attribute_created else attribute_uuid),
            key=submitted_values["key"],
        )

        if key_error:
            return JsonResponse(
                {
                    "success": False,
                    "errors": {
                        "key": key_error,
                    },
                    "error": key_error,
                },
                status=400,
            )

        proposal = ProposalService.get_or_create_working(
            model=model,
            user=request.user,
        )

        # -------------------------------------------------------------
        # For each field:
        #
        #   submitted == canonical/effective-without-own-change
        #       -> discard field proposal
        #
        #   submitted != canonical
        #       -> create/update field proposal
        # -------------------------------------------------------------

        canonical_values = None

        if attribute:
            canonical_values = _attribute_canonical_values(
                attribute,
            )
        else:
            create_change = _attribute_create_change(
                attribute_uuid,
                proposal,
            )

            if create_change:
                create_after = create_change.after or {}

                canonical_values = {
                    "name": create_after.get(
                        "name",
                        "",
                    ),
                    "key": create_after.get(
                        "key",
                        "",
                    ),
                    "data_type": create_after.get(
                        "data_type",
                        AttributeDefinition.DataType.TEXT,
                    ),
                    "description": create_after.get(
                        "description",
                        "",
                    ),
                    "required": create_after.get(
                        "required",
                        False,
                    ),
                    "default_value": create_after.get(
                        "default_value",
                        None,
                    ),
                    "sort_order": create_after.get(
                        "sort_order",
                        0,
                    ),
                }

        existing_update_changes = {
            change.after.get("field"): change
            for change in (
                proposal.changes.filter(
                    target_type="AttributeDefinition",
                    target_id=attribute_uuid,
                    operation=ProposalChange.Operation.UPDATE,
                )
            )
            if change.after and change.after.get("field")
        }

        changed = False

        for field in ATTRIBUTE_EDITABLE_FIELDS:

            canonical_value = canonical_values[field]

            submitted_value = submitted_values[field]

            if submitted_value == canonical_value:

                # Reverting to canonical means there should be no
                # outstanding proposal for this field.
                if field in existing_update_changes:
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

            changed = True

        effective_attribute, effective_values, is_created = _proposed_attribute_values(
            attribute_uuid,
            object_type,
            proposal,
        )

        return JsonResponse(
            {
                "success": True,
                "changed": changed,
                "created": is_created,
                "attribute_id": str(
                    attribute_uuid,
                ),
                "values": {
                    field: _serialize_value(
                        effective_values[field],
                    )
                    for field in ATTRIBUTE_EDITABLE_FIELDS
                },
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
    # DISCARD ATTRIBUTE
    # =================================================================

    if request.method == "POST" and request.POST.get("action") == "discard_attribute":
        if object_type is None:
            return JsonResponse(
                {
                    "success": False,
                    "error": ("An object type is required."),
                },
                status=400,
            )

        attribute_id = request.POST.get(
            "attribute_id",
        )

        if not attribute_id:
            return JsonResponse(
                {
                    "success": False,
                    "error": ("Attribute ID is required."),
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
                    "error": ("Invalid attribute ID."),
                },
                status=400,
            )

        proposal = ProposalService.get_or_create_working(
            model=model,
            user=request.user,
        )

        attribute, effective_values, attribute_created = _proposed_attribute_values(
            attribute_uuid,
            object_type,
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
                    field: _serialize_value(
                        canonical_values[field],
                    )
                    for field in ATTRIBUTE_EDITABLE_FIELDS
                },
                "proposed": False,
            }
        )

    # =================================================================
    # OBJECTTYPE FIELD-LEVEL PROPOSAL EDITOR
    # =================================================================

    if request.method == "POST" and request.POST.get("field"):
        if object_type is None:
            return JsonResponse(
                {
                    "success": False,
                    "error": (
                        "Field-level editing is only available "
                        "for an existing object type."
                    ),
                },
                status=400,
            )

        field = request.POST.get(
            "field",
            "",
        ).strip()

        if field not in EDITABLE_FIELDS:
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

            if not proposal:
                return JsonResponse(
                    {
                        "success": False,
                        "error": ("There is no working proposal " "to discard."),
                    },
                    status=400,
                )

            ProposalService.discard_change(
                proposal=proposal,
                target_type="ObjectType",
                target_id=object_type.id,
                field=field,
            )

            canonical_values = _canonical_values(
                object_type,
            )

            return JsonResponse(
                {
                    "success": True,
                    "value": _serialize_value(
                        canonical_values[field],
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

        raw_value = request.POST.get(
            "value",
            "",
        )

        try:
            value = _coerce_field_value(
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

        validation_error = _validate_field(
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

        effective_values = _effective_values(
            object_type,
            proposal,
        )

        current_value = effective_values[field]

        has_existing_change = bool(
            proposal
            and proposal.changes.filter(
                target_type="ObjectType",
                target_id=object_type.id,
                operation=ProposalChange.Operation.UPDATE,
                after__field=field,
            ).exists()
        )

        if current_value == value:
            return JsonResponse(
                {
                    "success": True,
                    "value": _serialize_value(
                        current_value,
                    ),
                    "proposed": has_existing_change,
                }
            )

        proposal = ProposalService.get_or_create_working(
            model=model,
            user=request.user,
        )

        ProposalService.record_change(
            proposal=proposal,
            operation=ProposalChange.Operation.UPDATE,
            target_type="ObjectType",
            target_id=object_type.id,
            parent_type="Model",
            parent_id=model.id,
            field=field,
            before={
                "field": field,
                "value": current_value,
            },
            after={
                "field": field,
                "value": value,
            },
        )

        return JsonResponse(
            {
                "success": True,
                "value": _serialize_value(
                    value,
                ),
                "proposed": True,
            }
        )

    # =================================================================
    # CREATE OBJECTTYPE
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
            errors["key"] = "An object type with this key already exists."

        if errors:
            effective_values = {
                "name": name,
                "key": key,
                "description": description,
                "is_active": True,
                "sort_order": 0,
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
            operation=ProposalChange.Operation.CREATE,
            target_type="ObjectType",
            target_id=object_type_uuid,
            parent_type="Model",
            parent_id=model.id,
            before=None,
            after={
                "name": name,
                "key": key,
                "description": description,
                "is_active": True,
                "sort_order": 0,
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
        effective_values = _effective_values(
            object_type,
            proposal,
        )
    else:
        effective_values = {
            "name": "",
            "key": "",
            "description": "",
            "is_active": True,
            "sort_order": 0,
        }

    return _render_editor(
        request=request,
        context=context,
        model=model,
        object_type=object_type,
        proposal=proposal,
        effective_values=effective_values,
    )
