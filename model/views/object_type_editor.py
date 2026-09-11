import uuid

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
    Return the effective ObjectType state.

    Canonical values are overlaid with any field-level changes in the
    current working proposal.
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

        if field in values and field in after:
            values[field] = after[field]

    return values


def _proposed_fields(object_type, proposal):
    """
    Return whether each ObjectType field currently has a proposal.
    """
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
# AttributeDefinition helpers
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


def _attribute_effective_values(attribute, proposal):
    """
    Return the effective AttributeDefinition state.

    Canonical values are overlaid with any field-level proposal changes.
    """
    values = _attribute_canonical_values(attribute)

    if not proposal:
        return values

    changes = proposal.changes.filter(
        target_type="AttributeDefinition",
        target_id=attribute.id,
        operation=ProposalChange.Operation.UPDATE,
    )

    for change in changes:
        after = change.after or {}
        field = after.get("field")

        if field in values and field in after:
            values[field] = after[field]

    return values


def _attribute_proposed_fields(attribute, proposal):
    """
    Return whether each AttributeDefinition field currently has a
    proposal.
    """
    result = {field: False for field in ATTRIBUTE_EDITABLE_FIELDS}

    if not attribute or not proposal:
        return result

    changes = proposal.changes.filter(
        target_type="AttributeDefinition",
        target_id=attribute.id,
        operation=ProposalChange.Operation.UPDATE,
    )

    for change in changes:
        after = change.after or {}
        field = after.get("field")

        if field in result:
            result[field] = True

    return result


def _get_attributes(object_type):
    if not object_type:
        return []

    return AttributeDefinition.objects.filter(
        object_type=object_type,
    ).order_by(
        "sort_order",
        "name",
    )


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
    """
    Convert Python values to the string representation expected by
    the browser-side proposal editor.
    """
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
            return "An object type with this key already exists."

        return None

    if field == "description":
        return None

    if field == "is_active":
        return None

    if field == "sort_order":
        return None

    return "Unsupported field."


# =====================================================================
# Attribute form handling
# =====================================================================


def _coerce_attribute_data(
    attribute,
    request,
):
    """
    Read and validate the complete AttributeDefinition editor.
    """

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
        "",
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
        str(attribute.sort_order),
    ).strip()

    errors = {}

    # -------------------------------------------------------------
    # Name
    # -------------------------------------------------------------

    if not name:
        errors["name"] = "Name is required."

    elif len(name) > 100:
        errors["name"] = "Name cannot exceed 100 characters."

    # -------------------------------------------------------------
    # Key
    # -------------------------------------------------------------

    if not key:
        errors["key"] = "Key is required."

    elif len(key) > 100:
        errors["key"] = "Key cannot exceed 100 characters."

    duplicate_query = AttributeDefinition.objects.filter(
        object_type=attribute.object_type,
        key=key,
    ).exclude(
        id=attribute.id,
    )

    if duplicate_query.exists():
        errors["key"] = "An attribute with this key already exists."

    # -------------------------------------------------------------
    # Data type
    # -------------------------------------------------------------

    valid_data_types = {
        choice for choice, _label in AttributeDefinition.DataType.choices
    }

    if data_type not in valid_data_types:
        errors["data_type"] = "Invalid attribute data type."

    # -------------------------------------------------------------
    # Sort order
    # -------------------------------------------------------------

    try:
        sort_order = int(sort_order_raw)

        if sort_order < 0:
            errors["sort_order"] = "Sort order cannot be negative."

    except (TypeError, ValueError):
        sort_order = 0
        errors["sort_order"] = "Sort order must be a whole number."

    # -------------------------------------------------------------
    # Default value
    #
    # The current editor represents default value as text.
    # Preserve an empty value as None.
    # -------------------------------------------------------------

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


# =====================================================================
# Context / rendering
# =====================================================================


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
    attributes = list(_get_attributes(object_type))

    for attribute in attributes:

        attribute.proposed_values = _attribute_effective_values(
            attribute,
            proposal,
        )

        attribute.proposed_fields = _attribute_proposed_fields(
            attribute,
            proposal,
        )

        attribute.attribute_proposed = any(attribute.proposed_fields.values())

        attribute.data_type_choices = AttributeDefinition.DataType.choices

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
    # AttributeDefinition save
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

        attribute = AttributeDefinition.objects.filter(
            id=attribute_id,
            object_type=object_type,
        ).first()

        if attribute is None:
            return JsonResponse(
                {
                    "success": False,
                    "error": "Attribute not found.",
                },
                status=404,
            )

        submitted_values, errors = _coerce_attribute_data(
            attribute,
            request,
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

        # -------------------------------------------------------------
        # Current effective state.
        #
        # If a previous proposal already exists for an attribute field,
        # that proposed value becomes the "before" state for this edit.
        # -------------------------------------------------------------

        effective_values = _attribute_effective_values(
            attribute,
            proposal,
        )

        # -------------------------------------------------------------
        # Get or create the working proposal.
        # -------------------------------------------------------------

        proposal = ProposalService.get_or_create_working(
            model=model,
            user=request.user,
        )

        # -------------------------------------------------------------
        # Record changed fields individually.
        # -------------------------------------------------------------

        changed = False

        for field in ATTRIBUTE_EDITABLE_FIELDS:

            before_value = effective_values[field]
            after_value = submitted_values[field]

            if before_value == after_value:
                continue

            ProposalService.record_change(
                proposal=proposal,
                operation=ProposalChange.Operation.UPDATE,
                target_type="AttributeDefinition",
                target_id=attribute.id,
                parent_type="ObjectType",
                parent_id=object_type.id,
                field=field,
                before={
                    "field": field,
                    "value": before_value,
                },
                after={
                    "field": field,
                    "value": after_value,
                },
            )

            changed = True

        # -------------------------------------------------------------
        # Return the effective proposed values.
        # -------------------------------------------------------------

        effective_values = _attribute_effective_values(
            attribute,
            proposal,
        )

        return JsonResponse(
            {
                "success": True,
                "changed": changed,
                "attribute_id": str(
                    attribute.id,
                ),
                "values": {
                    field: _serialize_value(
                        effective_values[field],
                    )
                    for field in ATTRIBUTE_EDITABLE_FIELDS
                },
                "proposed_fields": (
                    _attribute_proposed_fields(
                        attribute,
                        proposal,
                    )
                ),
            }
        )

    # =================================================================
    # ObjectType field-level proposal editor
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

        # -------------------------------------------------------------
        # Discard ObjectType field
        # -------------------------------------------------------------

        if action == "discard":

            if not proposal:
                return JsonResponse(
                    {
                        "success": False,
                        "error": ("There is no working proposal " "to discard."),
                    },
                    status=400,
                )

            try:
                ProposalService.discard_change(
                    proposal=proposal,
                    target_type="ObjectType",
                    target_id=object_type.id,
                    field=field,
                )
            except ValueError as exc:
                return JsonResponse(
                    {
                        "success": False,
                        "error": str(exc),
                    },
                    status=400,
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

        # -------------------------------------------------------------
        # Invalid action
        # -------------------------------------------------------------

        if action:
            return JsonResponse(
                {
                    "success": False,
                    "error": "Invalid action.",
                },
                status=400,
            )

        # -------------------------------------------------------------
        # Save ObjectType field
        # -------------------------------------------------------------

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

        try:
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
        except ValueError as exc:
            return JsonResponse(
                {
                    "success": False,
                    "error": str(exc),
                },
                status=400,
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

        object_type_id = uuid.uuid4()

        ProposalService.record_change(
            proposal=proposal,
            operation=ProposalChange.Operation.CREATE,
            target_type="ObjectType",
            target_id=object_type_id,
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
