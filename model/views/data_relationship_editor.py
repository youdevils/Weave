import uuid
from types import SimpleNamespace

from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from model.models.object import Object
from model.models.proposal import ProposalChange
from model.models.relationship import Relationship
from model.models.relationship_type import RelationshipType
from model.models.relationship_type_rule import RelationshipTypeRule
from model.services.proposal.proposal import ProposalService
from model.services.validation.attributes import validate_attribute_value
from model.views.common_context import get_model_context
from model.views.data_context import (
    ATTRIBUTE_FIELD_PREFIX,
    attribute_field_name,
    build_relationship_attribute_definitions,
    coerce_attribute_value,
    relationship_create_change,
    relationship_effective_values,
)


def _serialize_value(value):
    if isinstance(value, bool):
        return "true" if value else "false"

    if value is None:
        return ""

    return str(value)


def _get_working_relationship(
    model,
    relationship_type,
    relationship_id,
    proposal,
):
    relationship = Relationship.objects.filter(
        id=relationship_id,
        model=model,
        relationship_type=relationship_type,
    ).select_related("subject", "object").first()

    if relationship is not None:
        return relationship, False

    create_change = relationship_create_change(
        relationship_id,
        proposal,
    )

    if create_change is None or str(create_change.parent_id) != str(relationship_type.id):
        return None, False

    after = create_change.after or {}

    subject = Object.objects.filter(id=after.get("subject_id")).first()
    obj = Object.objects.filter(id=after.get("object_id")).first()

    proposed = SimpleNamespace(
        id=create_change.target_id,
        model_id=model.id,
        relationship_type_id=relationship_type.id,
        subject=subject,
        object=obj,
        is_active=after.get("is_active", True),
        attributes=dict(after.get("attributes") or {}),
    )

    return proposed, True


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


def _allowed_endpoint_choices(relationship_type, model):
    rules = list(
        RelationshipTypeRule.objects.filter(
            relationship_type=relationship_type,
        ).select_related("subject_type", "object_type")
    )

    subject_type_ids = {rule.subject_type_id for rule in rules}
    object_type_ids = {rule.object_type_id for rule in rules}

    allowed_pairs = {(rule.subject_type_id, rule.object_type_id) for rule in rules}

    subjects = Object.objects.filter(
        model=model,
        object_type_id__in=subject_type_ids,
        is_active=True,
    ).select_related("object_type").order_by("object_type__name", "name")

    objects = Object.objects.filter(
        model=model,
        object_type_id__in=object_type_ids,
        is_active=True,
    ).select_related("object_type").order_by("object_type__name", "name")

    return subjects, objects, allowed_pairs


@login_required
def data_relationship_editor(
    request,
    model_id,
    relationship_type_id,
    relationship_id=None,
):
    context = get_model_context(
        request,
        model_id,
    )

    model = context["model"]
    proposal = context["my_working_proposal"]

    relationship_type = get_object_or_404(
        RelationshipType,
        id=relationship_type_id,
        model=model,
    )

    relationship = None
    proposal_only = False

    if relationship_id:

        relationship, proposal_only = _get_working_relationship(
            model,
            relationship_type,
            relationship_id,
            proposal,
        )

        if relationship is None:
            raise Http404("Relationship not found.")

    attribute_definitions = build_relationship_attribute_definitions(
        relationship_type,
        proposal,
    )

    # =================================================================
    # Lifecycle
    # =================================================================

    if (
        request.method == "POST"
        and request.POST.get("action") == "set_relationship_status"
    ):

        if relationship is None:
            return JsonResponse(
                {"success": False, "error": "Relationship not found."},
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
            proposal = ProposalService.get_or_create_working(
                model=model,
                user=request.user,
            )

        if proposal_only:

            create_change = relationship_create_change(
                relationship.id,
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

        canonical_active = relationship.is_active

        if desired_active == canonical_active:

            ProposalService.discard_change(
                proposal=proposal,
                target_type="Relationship",
                target_id=relationship.id,
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
            target_type="Relationship",
            target_id=relationship.id,
            parent_type="RelationshipType",
            parent_id=relationship_type.id,
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
        and request.POST.get("action") == "discard_relationship_status"
    ):

        if relationship is None:
            return JsonResponse(
                {"success": False, "error": "Relationship not found."},
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
                        "The lifecycle of a newly proposed relationship "
                        "cannot be independently discarded."
                    ),
                },
                status=400,
            )

        ProposalService.discard_change(
            proposal=proposal,
            target_type="Relationship",
            target_id=relationship.id,
            field="is_active",
        )

        return JsonResponse(
            {
                "success": True,
                "value": _serialize_value(relationship.is_active),
            }
        )

    # =================================================================
    # Attribute-value editing
    #
    # Relationship has no top-level scalar fields other than is_active
    # (handled above), so the only field editable this way is a
    # dot-namespaced "attributes.<key>".
    # =================================================================

    if request.method == "POST" and request.POST.get("field"):

        if relationship is None:
            return JsonResponse(
                {"success": False, "error": "Relationship not found."},
                status=404,
            )

        field = request.POST.get("field", "").strip()

        if not field.startswith(ATTRIBUTE_FIELD_PREFIX):
            return JsonResponse(
                {"success": False, "error": "Unsupported field."},
                status=400,
            )

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

        action = request.POST.get("action", "").strip()

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
                            "available for a newly proposed relationship."
                        ),
                    },
                    status=400,
                )

            ProposalService.discard_change(
                proposal=proposal,
                target_type="Relationship",
                target_id=relationship.id,
                field=field,
            )

            canonical_value = (relationship.attributes or {}).get(attribute_key)

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

        if proposal is None:
            proposal = ProposalService.get_or_create_working(
                model=model,
                user=request.user,
            )

        if proposal_only:

            create_change = relationship_create_change(
                relationship.id,
                proposal,
            )

            after = dict(create_change.after or {})
            attributes = dict(after.get("attributes") or {})
            attributes[attribute_key] = value
            after["attributes"] = attributes
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

        canonical_value = (relationship.attributes or {}).get(attribute_key)

        if value == canonical_value:

            ProposalService.discard_change(
                proposal=proposal,
                target_type="Relationship",
                target_id=relationship.id,
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
            target_type="Relationship",
            target_id=relationship.id,
            parent_type="RelationshipType",
            parent_id=relationship_type.id,
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
    # Create Relationship
    # =================================================================

    if request.method == "POST" and relationship is None:

        subject_choices, object_choices, allowed_pairs = _allowed_endpoint_choices(
            relationship_type,
            model,
        )

        subject_id = request.POST.get("subject_id", "")
        object_id = request.POST.get("object_id", "")

        errors = {}

        subject = subject_choices.filter(id=subject_id).first() if subject_id else None
        obj = object_choices.filter(id=object_id).first() if object_id else None

        if not subject:
            errors["subject_id"] = "Choose a subject."

        if not obj:
            errors["object_id"] = "Choose an object."

        if (
            subject
            and obj
            and (subject.object_type_id, obj.object_type_id) not in allowed_pairs
        ):
            errors["object_id"] = (
                "This combination of types is not permitted by the "
                "relationship's rules."
            )

        attributes = {}

        for definition in attribute_definitions:

            raw_value = request.POST.get(f"attr_{definition.key}", "")

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
                "model/data_relationship_editor.html",
                {
                    **context,
                    "relationship_type": relationship_type,
                    "relationship": None,
                    "attribute_definitions": _decorate_for_form(
                        attribute_definitions,
                        raw_values,
                        errors,
                    ),
                    "subject_choices": subject_choices,
                    "object_choices": object_choices,
                    "form_values": {
                        "subject_id": subject_id,
                        "object_id": object_id,
                    },
                    "errors": errors,
                },
            )

        if proposal is None:
            proposal = ProposalService.get_or_create_working(
                model=model,
                user=request.user,
            )

        relationship_uuid = uuid.uuid4()

        ProposalService.record_change(
            proposal=proposal,
            operation=ProposalChange.Operation.CREATE,
            target_type="Relationship",
            target_id=relationship_uuid,
            parent_type="RelationshipType",
            parent_id=relationship_type.id,
            before=None,
            after={
                "subject_id": str(subject.id),
                "object_id": str(obj.id),
                "is_active": True,
                "attributes": attributes,
            },
        )

        return redirect(
            "model:data_relationship_edit",
            model.id,
            relationship_type.id,
            relationship_uuid,
        )

    # =================================================================
    # GET
    # =================================================================

    if relationship is None:

        subject_choices, object_choices, _allowed_pairs = _allowed_endpoint_choices(
            relationship_type,
            model,
        )

        return render(
            request,
            "model/data_relationship_editor.html",
            {
                **context,
                "relationship_type": relationship_type,
                "relationship": None,
                "attribute_definitions": _decorate_for_form(
                    attribute_definitions,
                    {},
                ),
                "subject_choices": subject_choices,
                "object_choices": object_choices,
                "form_values": {
                    "subject_id": "",
                    "object_id": "",
                },
                "errors": {},
            },
        )

    effective_values = relationship_effective_values(
        relationship,
        proposal,
    ) if not proposal_only else {
        "is_active": relationship.is_active,
        "attributes": relationship.attributes,
    }

    proposed_fields = {
        "is_active": False,
    }

    for definition in attribute_definitions:
        proposed_fields[attribute_field_name(definition.key)] = False

    if proposal_only:

        for field in proposed_fields:
            proposed_fields[field] = True

    elif proposal:

        for change in proposal.changes.filter(
            target_type="Relationship",
            target_id=relationship.id,
            operation=ProposalChange.Operation.UPDATE,
        ):
            after = change.after or {}
            field = after.get("field")

            if field in proposed_fields:
                proposed_fields[field] = True

    return render(
        request,
        "model/data_relationship_editor.html",
        {
            **context,
            "relationship_type": relationship_type,
            "relationship": relationship,
            "proposal": proposal,
            "proposal_only": proposal_only,
            "proposed_values": effective_values,
            "proposed_fields": proposed_fields,
            "attribute_definitions": _decorate_for_edit(
                attribute_definitions,
                effective_values["attributes"],
                proposed_fields,
            ),
            "proposal_update_url": request.path,
        },
    )
