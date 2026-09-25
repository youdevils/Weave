import uuid
from types import SimpleNamespace

from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render

from model.models.object import Object
from model.models.proposal import ProposalChange
from model.models.relationship import Relationship
from model.services.proposal.proposal import ProposalService
from model.services.validation.attributes import validate_attribute_value
from model.services.validation.fields import RELATIONSHIP_ENDPOINT_FIELDS
from model.views.active_proposal import get_or_create_active_proposal
from model.views.common_context import get_model_context
from model.views.sidebar import with_updated_sidebar
from model.views.data_context import (
    ATTRIBUTE_FIELD_PREFIX,
    attribute_field_name,
    build_proposed_only_objects,
    build_relationship_attribute_definitions,
    coerce_attribute_value,
    relationship_create_change,
    relationship_effective_values,
    resolve_relationship_endpoint,
    resolve_working_relationship_type,
)

_ENDPOINT_REQUIRED_MESSAGES = {
    "subject_id": "Choose a subject.",
    "object_id": "Choose an object.",
}

_ENDPOINT_PAIR_MESSAGE = (
    "This combination of types is not permitted by the "
    "relationship's rules."
)


def _serialize_value(value):
    if isinstance(value, bool):
        return "true" if value else "false"

    if value is None:
        return ""

    return str(value)


def _endpoint_label(object_id, proposal):
    endpoint = resolve_relationship_endpoint(object_id, proposal)

    return endpoint.name if endpoint is not None else ""


def _effective_endpoint_ids(relationship, proposal, proposal_only):
    """
    The relationship's current {subject_id, object_id} as strings —
    from its CREATE payload when proposal-only, otherwise canonical
    with any pending endpoint UPDATEs applied.
    """

    if proposal_only:
        after = relationship_create_change(relationship.id, proposal).after or {}

        return {field: str(after.get(field) or "") for field in RELATIONSHIP_ENDPOINT_FIELDS}

    effective = relationship_effective_values(relationship, proposal)

    return {field: effective[field] for field in RELATIONSHIP_ENDPOINT_FIELDS}


def _with_current_choice(choices, current, object_type_lookup):
    """
    Keep the relationship's current endpoint selectable in its picker
    even when it would no longer be offered for a new relationship
    (e.g. it has since been retired), so opening the editor never
    silently shows a different selection from the one recorded.
    """

    if current is None or _find_candidate(choices, current.id) is not None:
        return choices

    working_type = object_type_lookup.get(str(current.object_type_id))

    if working_type is None:
        return choices

    return sorted(
        [
            *choices,
            SimpleNamespace(
                id=current.id,
                name=current.name,
                object_type_id=current.object_type_id,
                object_type=working_type,
            ),
        ],
        key=lambda item: (item.object_type.name, item.name),
    )


def _get_working_relationship(
    model,
    relationship_type,
    relationship_id,
    proposal,
):
    relationship = Relationship.objects.filter(
        id=relationship_id,
        model=model,
        relationship_type_id=relationship_type.id,
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

    subject = resolve_relationship_endpoint(after.get("subject_id"), proposal)
    obj = resolve_relationship_endpoint(after.get("object_id"), proposal)

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


def _endpoint_candidates(type_ids, object_type_lookup, model, proposal):
    """
    Uniform candidate list (SimpleNamespace) for one side of the
    relationship picker: canonical Objects (active, of an allowed
    type) plus proposal-only CREATE Objects of the same allowed
    types. Every item exposes .id/.name/.object_type_id/.object_type
    (a working ObjectType item from context["object_types"], reused
    by reference across every candidate of the same type so
    {% regroup %} groups canonical and proposed candidates under one
    header, not two).
    """

    candidates = []

    canonical = (
        Object.objects.filter(model=model, object_type_id__in=type_ids, is_active=True)
        .select_related("object_type")
        .order_by("object_type__name", "name")
    )

    for obj in canonical:
        working_type = object_type_lookup.get(str(obj.object_type_id), obj.object_type)
        candidates.append(
            SimpleNamespace(
                id=obj.id,
                name=obj.name,
                object_type_id=obj.object_type_id,
                object_type=working_type,
            )
        )

    for type_id in type_ids:
        working_type = object_type_lookup.get(str(type_id))
        if working_type is None:
            continue
        for proposed in build_proposed_only_objects(working_type, proposal):
            candidates.append(
                SimpleNamespace(
                    id=proposed.id,
                    name=proposed.name,
                    object_type_id=proposed.object_type_id,
                    object_type=working_type,
                )
            )

    candidates.sort(key=lambda item: (item.object_type.name, item.name))
    return candidates


def _allowed_endpoint_choices(relationship_type, model, proposal, object_type_lookup):
    """
    Sources rules from relationship_type.rules — already the
    effective, proposal-inclusive rule list built by
    common_context._build_working_relationship_types /
    _build_working_relationship_rules[_for_proposed_type] — instead of
    a fresh canonical RelationshipTypeRule query, so pending rule
    CREATEs (including under a proposal-only RelationshipType) are
    respected with zero extra queries.
    """

    rules = relationship_type.rules

    # Rule endpoint type ids come from real UUID model fields for a
    # canonical rule but as JSON-stored strings for a proposal-only
    # CREATE rule (see common_context._extract_created_rule_values) —
    # normalise to strings throughout so canonical/proposal-only rules
    # and canonical/proposal-only Object candidates compare correctly.
    allowed_pairs = {
        (str(rule.subject_type_id), str(rule.object_type_id)) for rule in rules
    }
    subject_type_ids = {rule.subject_type_id for rule in rules}
    object_type_ids = {rule.object_type_id for rule in rules}

    subject_choices = _endpoint_candidates(subject_type_ids, object_type_lookup, model, proposal)
    object_choices = _endpoint_candidates(object_type_ids, object_type_lookup, model, proposal)

    return subject_choices, object_choices, allowed_pairs


def _find_candidate(candidates, candidate_id):
    if not candidate_id:
        return None

    for candidate in candidates:
        if str(candidate.id) == str(candidate_id):
            return candidate

    return None


@login_required
@with_updated_sidebar
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
    proposal = context["active_proposal"]

    relationship_type = resolve_working_relationship_type(context, relationship_type_id)

    if relationship_type is None:
        raise Http404("Relationship type not found.")

    object_type_lookup = {str(ot.id): ot for ot in context["object_types"]}

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
            proposal, error_response = get_or_create_active_proposal(
                request,
                model,
                request.user,
            )
            if error_response is not None:
                return error_response

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
    # Endpoint editing (subject_id / object_id)
    #
    # Mirrors the Object record editor's property editing: a field-level
    # UPDATE against a canonical Relationship, or an edit of the CREATE
    # payload of a proposal-only one. The chosen Object must be one the
    # create form would offer, and the resulting subject/object type pair
    # must be permitted by the relationship's rules — the same checks the
    # create form applies. Cardinality is left to submission validation,
    # exactly as it is for create and retire.
    # =================================================================

    if (
        request.method == "POST"
        and request.POST.get("field", "").strip() in RELATIONSHIP_ENDPOINT_FIELDS
    ):

        if relationship is None:
            return JsonResponse(
                {"success": False, "error": "Relationship not found."},
                status=404,
            )

        field = request.POST.get("field", "").strip()
        other_field = "object_id" if field == "subject_id" else "subject_id"

        action = request.POST.get("action", "").strip()

        canonical_value = None if proposal_only else str(getattr(relationship, field))

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

            return JsonResponse(
                {
                    "success": True,
                    "value": canonical_value,
                    "display": _endpoint_label(canonical_value, proposal),
                    "proposed": False,
                }
            )

        if action:
            return JsonResponse(
                {"success": False, "error": "Invalid action."},
                status=400,
            )

        value = request.POST.get("value", "").strip()

        if value == canonical_value:

            if proposal is not None:
                ProposalService.discard_change(
                    proposal=proposal,
                    target_type="Relationship",
                    target_id=relationship.id,
                    field=field,
                )

            return JsonResponse(
                {
                    "success": True,
                    "value": canonical_value,
                    "display": _endpoint_label(canonical_value, proposal),
                    "proposed": False,
                }
            )

        subject_choices, object_choices, allowed_pairs = _allowed_endpoint_choices(
            relationship_type,
            model,
            proposal,
            object_type_lookup,
        )

        candidate = _find_candidate(
            subject_choices if field == "subject_id" else object_choices,
            value,
        )

        if candidate is None:
            return JsonResponse(
                {"success": False, "error": _ENDPOINT_REQUIRED_MESSAGES[field]},
                status=400,
            )

        other = resolve_relationship_endpoint(
            _effective_endpoint_ids(relationship, proposal, proposal_only)[other_field],
            proposal,
        )

        if field == "subject_id":
            pair = (str(candidate.object_type_id), str(getattr(other, "object_type_id", "")))
        else:
            pair = (str(getattr(other, "object_type_id", "")), str(candidate.object_type_id))

        if other is None or pair not in allowed_pairs:
            return JsonResponse(
                {"success": False, "error": _ENDPOINT_PAIR_MESSAGE},
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

            create_change = relationship_create_change(
                relationship.id,
                proposal,
            )

            after = dict(create_change.after or {})
            after[field] = str(candidate.id)
            create_change.after = after
            create_change.save(update_fields=["after", "updated_at"])
            ProposalService.reset_validation(proposal)

        else:

            ProposalService.record_change(
                proposal=proposal,
                operation=ProposalChange.Operation.UPDATE,
                target_type="Relationship",
                target_id=relationship.id,
                parent_type="RelationshipType",
                parent_id=relationship_type.id,
                field=field,
                before={"field": field, "value": canonical_value},
                after={"field": field, "value": str(candidate.id)},
            )

        return JsonResponse(
            {
                "success": True,
                "value": str(candidate.id),
                "display": candidate.name,
                "proposed": True,
            }
        )

    # =================================================================
    # Attribute-value editing
    #
    # Endpoints are handled above and is_active by the lifecycle
    # actions, so the only field editable this way is a dot-namespaced
    # "attributes.<key>".
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
            proposal, error_response = get_or_create_active_proposal(
                request,
                model,
                request.user,
            )
            if error_response is not None:
                return error_response

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
            proposal,
            object_type_lookup,
        )

        subject_id = request.POST.get("subject_id", "")
        object_id = request.POST.get("object_id", "")

        errors = {}

        subject = _find_candidate(subject_choices, subject_id)
        obj = _find_candidate(object_choices, object_id)

        if not subject:
            errors["subject_id"] = "Choose a subject."

        if not obj:
            errors["object_id"] = "Choose an object."

        if (
            subject
            and obj
            and (str(subject.object_type_id), str(obj.object_type_id)) not in allowed_pairs
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
            proposal, error_response = get_or_create_active_proposal(
                request,
                model,
                request.user,
            )
            if error_response is not None:
                return error_response

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
            proposal,
            object_type_lookup,
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
        **_effective_endpoint_ids(relationship, proposal, proposal_only),
    }

    proposed_fields = {
        "is_active": False,
        "subject_id": False,
        "object_id": False,
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

    # Effective endpoints: the recorded ones unless a pending UPDATE
    # re-points them.
    subject_endpoint = relationship.subject
    object_endpoint = relationship.object

    if proposed_fields["subject_id"] and not proposal_only:
        subject_endpoint = resolve_relationship_endpoint(
            effective_values["subject_id"], proposal,
        ) or subject_endpoint

    if proposed_fields["object_id"] and not proposal_only:
        object_endpoint = resolve_relationship_endpoint(
            effective_values["object_id"], proposal,
        ) or object_endpoint

    subject_choices, object_choices, _allowed_pairs = _allowed_endpoint_choices(
        relationship_type,
        model,
        proposal,
        object_type_lookup,
    )

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
            "subject_endpoint": subject_endpoint,
            "object_endpoint": object_endpoint,
            "subject_choices": _with_current_choice(
                subject_choices, subject_endpoint, object_type_lookup,
            ),
            "object_choices": _with_current_choice(
                object_choices, object_endpoint, object_type_lookup,
            ),
            "proposal_update_url": request.path,
        },
    )
