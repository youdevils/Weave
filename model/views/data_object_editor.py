import uuid
from types import SimpleNamespace

from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render

from model.models.object import Object
from model.models.proposal import ProposalChange
from model.services.proposal.proposal import ProposalService
from model.services.validation.attributes import validate_attribute_value
from model.views.active_proposal import get_or_create_active_proposal
from model.views.common_context import get_model_context
from model.views.sidebar import with_updated_sidebar
from model.views.data_context import (
    ATTRIBUTE_FIELD_PREFIX,
    attribute_field_name,
    build_object_attribute_definitions,
    coerce_attribute_value,
    object_create_change,
    object_effective_values,
    resolve_working_object_type,
)

OBJECT_PROPERTY_FIELDS = {
    "name",
    "description",
}


def _serialize_value(value):
    if isinstance(value, bool):
        return "true" if value else "false"

    if value is None:
        return ""

    return str(value)


def _get_working_object(
    model,
    object_type,
    object_id,
    proposal,
):
    """
    Resolve an Object either from the canonical database or, if it
    doesn't exist there yet, from a proposal-only CREATE change in the
    current working proposal. Returns (obj, proposal_only) or
    (None, False) if nothing matches.
    """

    obj = Object.objects.filter(
        id=object_id,
        model=model,
        object_type_id=object_type.id,
    ).first()

    if obj is not None:
        return obj, False

    create_change = object_create_change(
        object_id,
        proposal,
    )

    if create_change is None or str(create_change.parent_id) != str(object_type.id):
        return None, False

    after = create_change.after or {}

    proposed = SimpleNamespace(
        id=create_change.target_id,
        model_id=model.id,
        object_type_id=object_type.id,
        name=after.get("name", ""),
        description=after.get("description", ""),
        is_active=after.get("is_active", True),
        attributes=dict(after.get("attributes") or {}),
    )

    return proposed, True


def _validate_object_property(
    field,
    value,
):
    if field == "name":

        if not value:
            return "Name is required."

        if len(value) > 255:
            return "Name cannot exceed 255 characters."

    return None


def _resolve_attribute_definition(
    definitions,
    key,
):
    for definition in definitions:
        if definition.key == key:
            return definition

    return None


def _decorate_for_form(
    definitions,
    raw_values,
    errors=None,
):
    """
    Attach per-attribute render metadata for the create-record form.
    Django templates can't index a dict by a loop variable, so the
    values a field needs are attached directly to each definition
    instead.
    """

    errors = errors or {}

    for definition in definitions:
        definition.field_name = f"attr_{definition.key}"
        definition.raw_value = raw_values.get(definition.key, "")
        definition.choices = (definition.config or {}).get("choices", [])
        definition.error = errors.get(f"attr_{definition.key}")

    return definitions


def _decorate_for_edit(
    definitions,
    effective_attributes,
    proposed_fields,
):
    for definition in definitions:
        field_name = attribute_field_name(definition.key)
        definition.field_name = field_name
        definition.current_value = effective_attributes.get(definition.key)
        definition.is_proposed = proposed_fields.get(field_name, False)
        definition.choices = (definition.config or {}).get("choices", [])

    return definitions


@login_required
@with_updated_sidebar
def data_object_editor(
    request,
    model_id,
    object_type_id,
    object_id=None,
):
    context = get_model_context(
        request,
        model_id,
    )

    model = context["model"]
    proposal = context["active_proposal"]

    object_type = resolve_working_object_type(context, object_type_id)

    if object_type is None:
        raise Http404("Object type not found.")

    obj = None
    proposal_only = False

    if object_id:

        obj, proposal_only = _get_working_object(
            model,
            object_type,
            object_id,
            proposal,
        )

        if obj is None:
            raise Http404("Object not found.")

    attribute_definitions = build_object_attribute_definitions(
        object_type,
        proposal,
    )

    # =================================================================
    # Lifecycle
    # =================================================================

    if (
        request.method == "POST"
        and request.POST.get("action") == "set_object_status"
    ):

        if obj is None:
            return JsonResponse(
                {"success": False, "error": "Object not found."},
                status=404,
            )

        desired = str(request.POST.get("is_active", "")).strip().lower()

        if desired not in {"true", "false"}:
            return JsonResponse(
                {"success": False, "error": "Status must be true or false."},
                status=400,
            )

        desired_active = desired == "true"

        if proposal is None:
            proposal, error_response = get_or_create_active_proposal(
                request,
                model,
                request.user,
            )
            if error_response is not None:
                return error_response

        if proposal_only:

            create_change = object_create_change(
                obj.id,
                proposal,
            )

            after = dict(create_change.after or {})
            after["is_active"] = desired_active
            create_change.after = after
            create_change.save(update_fields=["after", "updated_at"])
            ProposalService.reset_validation(proposal)

            return JsonResponse(
                {
                    "success": True,
                    "value": _serialize_value(desired_active),
                    "proposed": True,
                }
            )

        canonical_active = obj.is_active

        if desired_active == canonical_active:

            ProposalService.discard_change(
                proposal=proposal,
                target_type="Object",
                target_id=obj.id,
                field="is_active",
            )

            return JsonResponse(
                {
                    "success": True,
                    "value": _serialize_value(canonical_active),
                    "proposed": False,
                }
            )

        ProposalService.record_change(
            proposal=proposal,
            operation=ProposalChange.Operation.UPDATE,
            target_type="Object",
            target_id=obj.id,
            parent_type="ObjectType",
            parent_id=object_type.id,
            field="is_active",
            before={"field": "is_active", "value": canonical_active},
            after={"field": "is_active", "value": desired_active},
        )

        return JsonResponse(
            {
                "success": True,
                "value": _serialize_value(desired_active),
                "proposed": True,
            }
        )

    if (
        request.method == "POST"
        and request.POST.get("action") == "discard_object_status"
    ):

        if obj is None:
            return JsonResponse(
                {"success": False, "error": "Object not found."},
                status=404,
            )

        if proposal is None:
            return JsonResponse(
                {"success": False, "error": "There is no working proposal to discard."},
                status=400,
            )

        if proposal_only:
            return JsonResponse(
                {
                    "success": False,
                    "error": (
                        "The lifecycle of a newly proposed object "
                        "cannot be independently discarded."
                    ),
                },
                status=400,
            )

        ProposalService.discard_change(
            proposal=proposal,
            target_type="Object",
            target_id=obj.id,
            field="is_active",
        )

        return JsonResponse(
            {
                "success": True,
                "value": _serialize_value(obj.is_active),
            }
        )

    # =================================================================
    # Property / attribute-value editing
    # =================================================================

    if request.method == "POST" and request.POST.get("field"):

        if obj is None:
            return JsonResponse(
                {"success": False, "error": "Object not found."},
                status=404,
            )

        field = request.POST.get("field", "").strip()
        is_attribute_field = field.startswith(ATTRIBUTE_FIELD_PREFIX)

        if not is_attribute_field and field not in OBJECT_PROPERTY_FIELDS:
            return JsonResponse(
                {"success": False, "error": "Unsupported field."},
                status=400,
            )

        action = request.POST.get("action", "").strip()

        attribute_key = None
        attribute_definition = None

        if is_attribute_field:

            attribute_key = field[len(ATTRIBUTE_FIELD_PREFIX):]

            attribute_definition = _resolve_attribute_definition(
                attribute_definitions,
                attribute_key,
            )

            if attribute_definition is None:
                return JsonResponse(
                    {"success": False, "error": "Unknown attribute."},
                    status=400,
                )

        # -------------------------------------------------------------
        # Discard property proposal
        # -------------------------------------------------------------

        if action == "discard":

            if proposal is None:
                return JsonResponse(
                    {"success": False, "error": "There is no working proposal to discard."},
                    status=400,
                )

            if proposal_only:
                return JsonResponse(
                    {
                        "success": False,
                        "error": (
                            "Individual property discard is not "
                            "available for a newly proposed object."
                        ),
                    },
                    status=400,
                )

            ProposalService.discard_change(
                proposal=proposal,
                target_type="Object",
                target_id=obj.id,
                field=field,
            )

            if is_attribute_field:
                canonical_value = (obj.attributes or {}).get(attribute_key)
            else:
                canonical_value = getattr(obj, field)

            return JsonResponse(
                {
                    "success": True,
                    "value": _serialize_value(canonical_value),
                    "proposed": False,
                }
            )

        if action:
            return JsonResponse(
                {"success": False, "error": "Invalid action."},
                status=400,
            )

        raw_value = request.POST.get("value", "")

        if is_attribute_field:

            try:
                value = coerce_attribute_value(
                    attribute_definition.data_type,
                    raw_value,
                )
            except ValueError as exc:
                return JsonResponse(
                    {"success": False, "error": str(exc)},
                    status=400,
                )

            issue = validate_attribute_value(
                attribute_definition,
                value,
                field=attribute_key,
            )

            if issue is not None:
                return JsonResponse(
                    {"success": False, "error": issue.message},
                    status=400,
                )

        else:

            value = raw_value.strip() if isinstance(raw_value, str) else raw_value

            validation_error = _validate_object_property(field, value)

            if validation_error:
                return JsonResponse(
                    {"success": False, "error": validation_error},
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

            create_change = object_create_change(
                obj.id,
                proposal,
            )

            after = dict(create_change.after or {})

            if is_attribute_field:
                attributes = dict(after.get("attributes") or {})
                attributes[attribute_key] = value
                after["attributes"] = attributes
            else:
                after[field] = value

            create_change.after = after
            create_change.save(update_fields=["after", "updated_at"])
            ProposalService.reset_validation(proposal)

            return JsonResponse(
                {
                    "success": True,
                    "value": _serialize_value(value),
                    "proposed": True,
                }
            )

        if is_attribute_field:
            canonical_value = (obj.attributes or {}).get(attribute_key)
        else:
            canonical_value = getattr(obj, field)

        if value == canonical_value:

            ProposalService.discard_change(
                proposal=proposal,
                target_type="Object",
                target_id=obj.id,
                field=field,
            )

            return JsonResponse(
                {
                    "success": True,
                    "value": _serialize_value(canonical_value),
                    "proposed": False,
                }
            )

        ProposalService.record_change(
            proposal=proposal,
            operation=ProposalChange.Operation.UPDATE,
            target_type="Object",
            target_id=obj.id,
            parent_type="ObjectType",
            parent_id=object_type.id,
            field=field,
            before={"field": field, "value": canonical_value},
            after={"field": field, "value": value},
        )

        return JsonResponse(
            {
                "success": True,
                "value": _serialize_value(value),
                "proposed": True,
            }
        )

    # =================================================================
    # Create Object
    # =================================================================

    if request.method == "POST" and obj is None:

        name = request.POST.get("name", "").strip()
        description = request.POST.get("description", "").strip()

        errors = {}

        if not name:
            errors["name"] = "Name is required."
        elif len(name) > 255:
            errors["name"] = "Name cannot exceed 255 characters."

        attributes = {}

        for definition in attribute_definitions:

            raw_value = request.POST.get(
                f"attr_{definition.key}",
                "",
            )

            # An attribute left blank at creation time is simply not
            # set, matching validate_attributes' own semantics
            # (missing keys are only an error when required) — this
            # is distinct from explicitly clearing an existing value
            # to null on the record editor's field-level update path.
            if raw_value in (None, ""):

                if definition.required:
                    errors[f"attr_{definition.key}"] = (
                        f"{definition.name} is required."
                    )

                continue

            try:
                value = coerce_attribute_value(
                    definition.data_type,
                    raw_value,
                )
            except ValueError as exc:
                errors[f"attr_{definition.key}"] = str(exc)
                continue

            issue = validate_attribute_value(
                definition,
                value,
                field=definition.key,
            )

            if issue is not None:
                errors[f"attr_{definition.key}"] = issue.message
                continue

            attributes[definition.key] = value

        if errors:

            raw_values = {
                definition.key: request.POST.get(f"attr_{definition.key}", "")
                for definition in attribute_definitions
            }

            return render(
                request,
                "model/data_object_editor.html",
                {
                    **context,
                    "object_type": object_type,
                    "object": None,
                    "attribute_definitions": _decorate_for_form(
                        attribute_definitions,
                        raw_values,
                        errors,
                    ),
                    "form_values": {
                        "name": name,
                        "description": description,
                    },
                    "errors": errors,
                },
            )

        if proposal is None:
            proposal, error_response = get_or_create_active_proposal(
                request,
                model,
                request.user,
            )
            if error_response is not None:
                return error_response

        object_uuid = uuid.uuid4()

        ProposalService.record_change(
            proposal=proposal,
            operation=ProposalChange.Operation.CREATE,
            target_type="Object",
            target_id=object_uuid,
            parent_type="ObjectType",
            parent_id=object_type.id,
            before=None,
            after={
                "name": name,
                "description": description,
                "is_active": True,
                "attributes": attributes,
            },
        )

        return redirect(
            "model:data_object_edit",
            model.id,
            object_type.id,
            object_uuid,
        )

    # =================================================================
    # GET
    # =================================================================

    if obj is None:

        return render(
            request,
            "model/data_object_editor.html",
            {
                **context,
                "object_type": object_type,
                "object": None,
                "attribute_definitions": _decorate_for_form(
                    attribute_definitions,
                    {},
                ),
                "form_values": {
                    "name": "",
                    "description": "",
                },
                "errors": {},
            },
        )

    effective_values = object_effective_values(
        obj,
        proposal,
    ) if not proposal_only else {
        "name": obj.name,
        "description": obj.description,
        "is_active": obj.is_active,
        "attributes": obj.attributes,
    }

    proposed_fields = {
        "name": False,
        "description": False,
        "is_active": False,
    }

    for definition in attribute_definitions:
        proposed_fields[attribute_field_name(definition.key)] = False

    if proposal_only:

        for field in proposed_fields:
            proposed_fields[field] = True

    elif proposal:

        for change in proposal.changes.filter(
            target_type="Object",
            target_id=obj.id,
            operation=ProposalChange.Operation.UPDATE,
        ):
            after = change.after or {}
            field = after.get("field")

            if field in proposed_fields:
                proposed_fields[field] = True

    subject_relationship_groups = []
    object_relationship_groups = []

    if not proposal_only:
        subject_relationship_groups = _relationship_groups(
            obj.subject_relationships.select_related(
                "relationship_type",
                "object__object_type",
            ),
            endpoint="object",
        )
        object_relationship_groups = _relationship_groups(
            obj.object_relationships.select_related(
                "relationship_type",
                "subject__object_type",
            ),
            endpoint="subject",
        )

    return render(
        request,
        "model/data_object_editor.html",
        {
            **context,
            "object_type": object_type,
            "object": obj,
            "proposal": proposal,
            "proposal_only": proposal_only,
            "proposed_values": effective_values,
            "proposed_fields": proposed_fields,
            "attribute_definitions": _decorate_for_edit(
                attribute_definitions,
                effective_values["attributes"],
                proposed_fields,
            ),
            "subject_relationship_groups": subject_relationship_groups,
            "object_relationship_groups": object_relationship_groups,
            "proposal_update_url": request.path,
        },
    )


def _relationship_groups(
    relationships,
    endpoint,
):
    """
    Group a queryset of canonical Relationship rows by relationship
    type, for the record editor's read-only Relationships section.
    `endpoint` selects which side of each relationship (the *other*
    Object) to link to.
    """

    groups = {}

    for relationship in relationships:

        other = getattr(relationship, endpoint)

        group = groups.setdefault(
            relationship.relationship_type.name,
            {"label": relationship.relationship_type.name, "items": []},
        )

        group["items"].append(
            SimpleNamespace(
                object_id=other.id,
                object_type_id=other.object_type_id,
                name=other.name,
            )
        )

    return sorted(groups.values(), key=lambda group: group["label"])
