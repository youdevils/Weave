from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse

from model.access import get_bulk_editable_model
from model.services.proposal.bulk_edit import (
    LIFECYCLE_FIELD,
    MODE_NO_CHANGE,
    BulkEditValidationError,
    EmptySelectionError,
    FieldEdit,
    TooManySelectedError,
    UnresolvedSelectionError,
    apply_edits,
    collect_effective_state,
    compute_fingerprint,
    dedupe_and_bound,
    resolve_working_objects,
    validate_edits,
)
from model.services.field_paths import attribute_field_name
from model.views.active_proposal import get_or_create_active_proposal
from model.views.common_context import get_model_context
from model.views.data_context import build_object_attribute_definitions, resolve_working_object_type
from model.views.sidebar import with_updated_sidebar


def _parse_edits(post_data, attribute_definitions):

    edits = [
        FieldEdit(
            field=LIFECYCLE_FIELD,
            mode=post_data.get(f"mode__{LIFECYCLE_FIELD}", MODE_NO_CHANGE),
        )
    ]

    for definition in attribute_definitions:

        field = attribute_field_name(definition.key)

        edits.append(
            FieldEdit(
                field=field,
                mode=post_data.get(f"mode__{field}", MODE_NO_CHANGE),
                raw_value=post_data.get(f"value__{field}", ""),
            )
        )

    return edits


def _decorate_for_bulk_form(attribute_definitions, edits_by_field, effective, field_errors):
    """
    Django templates can't index a dict by a loop variable, so (as
    data_object_editor.py's own _decorate_for_edit/_decorate_for_form
    already do) the per-field values a template needs are attached
    directly to each definition instead.
    """

    for definition in attribute_definitions:
        field = attribute_field_name(definition.key)
        definition.field_name = field
        definition.choices = (definition.config or {}).get("choices", [])
        definition.edit = edits_by_field.get(field)
        definition.effective_field = effective.get(field, {})
        definition.error = field_errors.get(field)

    return attribute_definitions


def _render(request, context, object_type, objects, attribute_definitions, proposal, **extra):

    result = extra.get("result")
    field_errors = result.failures[0].field_errors if (result and result.failures) else {}
    edits_by_field = extra.get("edits_by_field", {})
    effective = collect_effective_state(objects, attribute_definitions, proposal)

    base = {
        **context,
        "object_type": object_type,
        "objects": objects,
        "attribute_definitions": _decorate_for_bulk_form(
            attribute_definitions, edits_by_field, effective, field_errors,
        ),
        "effective": effective,
        "object_ids": [str(obj.id) for obj, _ in objects],
        "field_errors": field_errors,
        "is_active_edit": edits_by_field.get(LIFECYCLE_FIELD),
        "is_active_effective": effective.get(LIFECYCLE_FIELD, {}),
        "is_active_error": field_errors.get(LIFECYCLE_FIELD),
    }

    base.update(extra)

    return render(request, "model/data_object_bulk_edit.html", base)


@login_required
@with_updated_sidebar
def data_object_bulk_edit(
    request,
    model_id,
    object_type_id,
):
    get_bulk_editable_model(request, model_id)

    context = get_model_context(
        request,
        model_id,
    )

    model = context["model"]
    proposal = context["active_proposal"]

    object_type = resolve_working_object_type(context, object_type_id)

    if object_type is None:
        raise Http404("Object type not found.")

    attribute_definitions = build_object_attribute_definitions(
        object_type,
        proposal,
    )

    if request.method != "POST":
        raise Http404("Select records from the index page first.")

    raw_ids = request.POST.getlist("object_id")

    try:
        object_ids = dedupe_and_bound(raw_ids)
    except (EmptySelectionError, TooManySelectedError) as exc:
        return render(
            request,
            "model/data_object_bulk_edit.html",
            {**context, "object_type": object_type, "selection_error": str(exc)},
            status=400,
        )

    try:
        objects = resolve_working_objects(model, object_type, proposal, object_ids)
    except UnresolvedSelectionError as exc:
        return render(
            request,
            "model/data_object_bulk_edit.html",
            {**context, "object_type": object_type, "selection_error": str(exc)},
            status=400,
        )

    action = request.POST.get("action", "")
    edits = _parse_edits(request.POST, attribute_definitions)
    edits_by_field = {edit.field: edit for edit in edits}

    # =================================================================
    # Preview — validate only, nothing is written.
    # =================================================================

    if action == "preview":

        result = validate_edits(objects, edits, attribute_definitions)

        fingerprint = (
            compute_fingerprint(
                model_id=model.id,
                object_type_id=object_type.id,
                object_ids=object_ids,
                edits=edits,
                proposal=proposal,
            )
            if result.ok
            else None
        )

        return _render(
            request, context, object_type, objects, attribute_definitions, proposal,
            edits_by_field=edits_by_field,
            result=result,
            previewed=result.ok,
            preview_fingerprint=fingerprint,
        )

    # =================================================================
    # Apply — re-validate and re-check the fingerprint; commit only if
    # both the operation is unchanged since Preview and still valid.
    # =================================================================

    if action == "apply":

        submitted_fingerprint = request.POST.get("preview_fingerprint", "")

        expected_fingerprint = compute_fingerprint(
            model_id=model.id,
            object_type_id=object_type.id,
            object_ids=object_ids,
            edits=edits,
            proposal=proposal,
        )

        result = validate_edits(objects, edits, attribute_definitions)
        fingerprint_matches = submitted_fingerprint == expected_fingerprint

        if not result.ok or not fingerprint_matches:
            return _render(
                request, context, object_type, objects, attribute_definitions, proposal,
                edits_by_field=edits_by_field,
                result=result,
                previewed=False,
                preview_fingerprint=None,
                stale_preview=(result.ok and not fingerprint_matches),
            )

        if proposal is None:
            proposal, error_response = get_or_create_active_proposal(
                request,
                model,
                request.user,
            )
            if error_response is not None:
                return error_response

        try:
            apply_edits(proposal, object_type, objects, edits, attribute_definitions)
        except BulkEditValidationError:
            # Defensive only: validate_edits above already re-checked the
            # same rules apply_edits re-runs, so this should not trigger.
            result = validate_edits(objects, edits, attribute_definitions)
            return _render(
                request, context, object_type, objects, attribute_definitions, proposal,
                edits_by_field=edits_by_field,
                result=result,
                previewed=False,
                preview_fingerprint=None,
            )

        return redirect(
            f"{reverse('model:data_objects', args=[model.id, object_type.id])}"
            f"?bulk_edited={len(objects)}"
        )

    # =================================================================
    # Bare load — the index page's selection form landed here directly;
    # no edits yet, everything defaults to "No change".
    # =================================================================

    return _render(
        request, context, object_type, objects, attribute_definitions, proposal,
        edits_by_field={},
        result=None,
        previewed=False,
        preview_fingerprint=None,
    )
