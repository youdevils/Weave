import json
import uuid
from types import SimpleNamespace

from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render

from model.models.attribute_definition import AttributeDefinition
from model.models.object_type import ObjectType
from model.models.proposal import ProposalChange
from model.services.appearance import OBJECT_TYPE, AppearanceService
from model.services.proposal.proposal import ProposalService
from model.views.active_proposal import get_or_create_active_proposal
from model.views.common_context import get_model_context
from model.views.sidebar import with_updated_sidebar

# =====================================================================
# Field definitions
# =====================================================================

OBJECT_TYPE_PROPERTY_FIELDS = {
    "name",
    "key",
    "description",
    "sort_order",
}

OBJECT_TYPE_LIFECYCLE_FIELD = "is_active"

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


# =====================================================================
# ObjectType helpers
# =====================================================================


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


def _object_type_effective_values(
    object_type,
    proposal,
):
    values = {
        "name": object_type.name,
        "key": object_type.key,
        "description": object_type.description,
        "sort_order": object_type.sort_order,
        "is_active": object_type.is_active,
    }

    if not proposal:
        return values

    for change in proposal.changes.filter(
        target_type="ObjectType",
        target_id=object_type.id,
        operation=ProposalChange.Operation.UPDATE,
    ).order_by("created_at"):

        after = change.after or {}
        field = after.get("field")

        if (
            field
            in OBJECT_TYPE_PROPERTY_FIELDS
            | {
                OBJECT_TYPE_LIFECYCLE_FIELD,
            }
            and "value" in after
        ):
            values[field] = after["value"]

    return values


def _object_type_proposed_fields(
    object_type_id,
    proposal,
):
    result = {
        field: False
        for field in (
            *OBJECT_TYPE_PROPERTY_FIELDS,
            OBJECT_TYPE_LIFECYCLE_FIELD,
        )
    }

    if not proposal:
        return result

    create_change = _object_type_create_change(
        object_type_id,
        proposal,
    )

    if create_change:
        for field in result:
            result[field] = True

    for change in proposal.changes.filter(
        target_type="ObjectType",
        target_id=object_type_id,
        operation=ProposalChange.Operation.UPDATE,
    ):
        after = change.after or {}
        field = after.get("field")

        if field in result:
            result[field] = True

    return result


# =====================================================================
# Attribute helpers
# =====================================================================


def _attribute_canonical_values(
    attribute,
):
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
    object_type,
    proposal,
):
    """
    Resolve either a canonical attribute or a proposal-only CREATE.
    """

    attribute = None

    if isinstance(
        object_type,
        ObjectType,
    ):
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

    changes = proposal.changes.filter(
        target_type="AttributeDefinition",
        target_id=attribute_id,
    ).order_by("created_at")

    for change in changes:

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
    object_type,
    proposal,
):
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

    # -------------------------------------------------------------
    # Canonical attributes
    # -------------------------------------------------------------

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

    # -------------------------------------------------------------
    # Proposed CREATE attributes
    # -------------------------------------------------------------

    if proposal and object_type:

        create_changes = proposal.changes.filter(
            target_type="AttributeDefinition",
            operation=ProposalChange.Operation.CREATE,
            parent_type="ObjectType",
            parent_id=object_type.id,
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
# Validation / coercion
# =====================================================================


def _serialize_value(
    value,
):
    if isinstance(
        value,
        bool,
    ):
        return "true" if value else "false"

    if isinstance(
        value,
        (dict, list),
    ):
        return json.dumps(value)

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


def _coerce_object_type_property(
    field,
    raw_value,
):
    if field in {
        "name",
        "key",
        "description",
    }:
        return raw_value.strip()

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


def _validate_object_type_property(
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

        if isinstance(
            object_type,
            ObjectType,
        ):
            query = query.exclude(
                id=object_type.id,
            )

        if query.exists():
            return "An object type with this key already exists."

        return None

    if field in {
        "description",
        "sort_order",
    }:
        return None

    return "Unsupported field."


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
        return "An attribute with this key already exists."

    return None


def _validate_proposed_attribute_key(
    proposal,
    object_type_id,
    attribute_id,
    key,
):
    if not proposal:
        return None

    create_changes = proposal.changes.filter(
        target_type="AttributeDefinition",
        operation=ProposalChange.Operation.CREATE,
        parent_type="ObjectType",
        parent_id=object_type_id,
    )

    for change in create_changes:

        if str(change.target_id) == str(attribute_id):
            continue

        after = change.after or {}

        if after.get("key") == key:
            return "An attribute with this key already exists."

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


def _get_working_object_type(
    context,
    object_type_id,
):
    """
    Resolve an ObjectType from the effective working-model context.

    The common context contains both canonical ObjectTypes and
    proposal-only CREATEs in the same working collection.
    """

    if not object_type_id:
        return None

    object_type_id = str(
        object_type_id,
    )

    for candidate in context.get(
        "object_types",
        [],
    ):
        if str(candidate.id) == object_type_id:
            return candidate

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
                if object_type
                else {
                    field: False
                    for field in (
                        *OBJECT_TYPE_PROPERTY_FIELDS,
                        OBJECT_TYPE_LIFECYCLE_FIELD,
                    )
                }
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
            # Style saves directly (never via the proposal); works for proposed-only types too.
            "appearance_form": (
                AppearanceService.type_form(model, OBJECT_TYPE, object_type.id) if object_type else None
            ),
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
@with_updated_sidebar
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
    proposal = context["active_proposal"]

    object_type = None
    proposal_only = False

    if object_type_id:

        object_type = ObjectType.objects.filter(
            id=object_type_id,
            model=model,
        ).first()

        if object_type is None:

            object_type = _get_working_object_type(
                context,
                object_type_id,
            )

            if object_type is None:
                raise Http404("Object type not found.")

            proposal_only = not isinstance(
                object_type,
                ObjectType,
            )

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
                    "error": "Object type not found.",
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
            proposal, error_response = get_or_create_active_proposal(
                request,
                model,
                request.user,
            )
            if error_response is not None:
                return error_response

        if proposal_only:

            create_change = _object_type_create_change(
                object_type.id,
                proposal,
            )

            if create_change is None:
                return JsonResponse(
                    {
                        "success": False,
                        "error": "Proposed object type not found.",
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
                    "value": _serialize_value(
                        canonical_active,
                    ),
                    "proposed": (
                        _object_type_proposed_fields(
                            object_type.id,
                            proposal,
                        )["is_active"]
                    ),
                }
            )

        ProposalService.record_change(
            proposal=proposal,
            operation=ProposalChange.Operation.UPDATE,
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
                "value": _serialize_value(
                    desired_active,
                ),
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
                    "error": "Object type not found.",
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
                        "ObjectType cannot be independently discarded."
                    ),
                },
                status=400,
            )

        ProposalService.discard_change(
            proposal=proposal,
            target_type="ObjectType",
            target_id=object_type.id,
            field="is_active",
        )

        return JsonResponse(
            {
                "success": True,
                "value": _serialize_value(
                    object_type.is_active,
                ),
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
                    "error": "Object type not found.",
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
            proposal, error_response = get_or_create_active_proposal(
                request,
                model,
                request.user,
            )
            if error_response is not None:
                return error_response

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
    # Create AttributeDefinition
    # =================================================================

    if request.method == "POST" and request.POST.get("action") == "create_attribute":

        if object_type is None:
            return JsonResponse(
                {
                    "success": False,
                    "error": "Object type not found.",
                },
                status=404,
            )

        if proposal is None:
            proposal, error_response = get_or_create_active_proposal(
                request,
                model,
                request.user,
            )
            if error_response is not None:
                return error_response

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
            object_type,
            ObjectType,
        ):

            canonical_key_error = _validate_attribute_key(
                object_type=object_type,
                attribute_id=None,
                key=submitted_values["key"],
            )

            if canonical_key_error:
                errors["key"] = canonical_key_error

        proposed_key_error = _validate_proposed_attribute_key(
            proposal=proposal,
            object_type_id=object_type.id,
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
            parent_type="ObjectType",
            parent_id=object_type.id,
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

        if object_type is None:
            return JsonResponse(
                {
                    "success": False,
                    "error": "Object type not found.",
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

        submitted_values, errors = _coerce_attribute_properties(
            request,
            effective_values,
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

        if proposal:

            proposed_key_error = _validate_proposed_attribute_key(
                proposal=proposal,
                object_type_id=object_type.id,
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
            proposal, error_response = get_or_create_active_proposal(
                request,
                model,
                request.user,
            )
            if error_response is not None:
                return error_response

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
            _attribute,
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

        if object_type is None:
            return JsonResponse(
                {
                    "success": False,
                    "error": "Object type not found.",
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
    # ObjectType property editing
    # =================================================================

    if request.method == "POST" and request.POST.get("field"):

        if object_type is None:
            return JsonResponse(
                {
                    "success": False,
                    "error": "Object type not found.",
                },
                status=404,
            )

        field = request.POST.get(
            "field",
            "",
        ).strip()

        if field not in OBJECT_TYPE_PROPERTY_FIELDS:
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
        # Discard property proposal
        # -------------------------------------------------------------

        if action == "discard":

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
                            "Individual property discard is not "
                            "available for a newly proposed ObjectType."
                        ),
                    },
                    status=400,
                )

            ProposalService.discard_change(
                proposal=proposal,
                target_type="ObjectType",
                target_id=object_type.id,
                field=field,
            )

            return JsonResponse(
                {
                    "success": True,
                    "value": _serialize_value(
                        getattr(
                            object_type,
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

        try:
            value = _coerce_object_type_property(
                field,
                request.POST.get(
                    "value",
                    "",
                ),
            )

        except ValueError as exc:
            return JsonResponse(
                {
                    "success": False,
                    "error": str(exc),
                },
                status=400,
            )

        validation_error = _validate_object_type_property(
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

        if proposal is None:
            proposal, error_response = get_or_create_active_proposal(
                request,
                model,
                request.user,
            )
            if error_response is not None:
                return error_response

        if proposal_only:

            create_change = _object_type_create_change(
                object_type.id,
                proposal,
            )

            if create_change is None:
                return JsonResponse(
                    {
                        "success": False,
                        "error": "Proposed object type not found.",
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
                    "value": _serialize_value(
                        value,
                    ),
                    "proposed": True,
                }
            )

        canonical_value = getattr(
            object_type,
            field,
        )

        if value == canonical_value:

            ProposalService.discard_change(
                proposal=proposal,
                target_type="ObjectType",
                target_id=object_type.id,
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
                "value": _serialize_value(
                    value,
                ),
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
            return _render_editor(
                request=request,
                context=context,
                model=model,
                object_type=None,
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

        if proposal is None:
            proposal, error_response = get_or_create_active_proposal(
                request,
                model,
                request.user,
            )
            if error_response is not None:
                return error_response

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
                "sort_order": 0,
                "is_active": True,
            },
        )

        return redirect(
            "model:object_type_edit",
            model.id,
            object_type_uuid,
        )

    # =================================================================
    # GET
    # =================================================================

    if object_type is None:

        effective_values = {
            "name": "",
            "key": "",
            "description": "",
            "sort_order": 0,
            "is_active": True,
        }

    else:
        effective_values = _object_type_effective_values(
            object_type,
            proposal,
        )

    return _render_editor(
        request=request,
        context=context,
        model=model,
        object_type=object_type,
        proposal=proposal,
        effective_values=effective_values,
    )
