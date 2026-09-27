from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render

from model.models.proposal import ProposalChange
from model.services.appearance import AppearanceService
from model.services.ontology_graph.compiler import compile_ontology_graph
from model.services.proposal.proposal import ProposalService
from model.services.proposal.submission import MODEL_EDITABLE_FIELDS
from model.views.active_proposal import get_or_create_active_proposal
from model.views.common_context import get_model_context
from model.views.sidebar import with_updated_sidebar

# Single source of truth is submission.MODEL_EDITABLE_FIELDS -- the point
# that actually writes a proposed Model field to the row. Aliased here so
# this view's pre-check (a fast, user-facing 400) always agrees with it.
EDITABLE_FIELDS = MODEL_EDITABLE_FIELDS


def _validate_model_field(
    field,
    value,
):
    if field == "name":

        if not value:
            return "Name is required."

        if len(value) > 200:
            return "Name cannot exceed 200 characters."

        return None

    return None


def _get_working_model_values(
    model,
    proposal,
):
    """
    Resolve the effective values for the editable Model fields.

    Canonical values come from the Model instance. Any matching UPDATE
    changes in the user's working proposal are overlaid on top.
    """

    values = {
        "name": model.name,
        "description": model.description,
        "purpose": model.purpose,
        "scope": model.scope,
        "exclusions": model.exclusions,
    }

    proposed_fields = set()

    if proposal:

        for change in proposal.changes.all():

            if (
                change.target_type != "Model"
                or change.target_id != model.id
                or change.operation != ProposalChange.Operation.UPDATE
            ):
                continue

            after = change.after or {}

            field = after.get("field")

            if field not in EDITABLE_FIELDS:
                continue

            if "value" not in after:
                continue

            values[field] = after["value"]
            proposed_fields.add(field)

    return values, proposed_fields


@login_required
@with_updated_sidebar
def overview(
    request,
    model_id,
):
    # =================================================================
    # Common model context
    # =================================================================

    context = get_model_context(
        request,
        model_id,
    )

    model = context["model"]
    proposal = context["active_proposal"]

    # =================================================================
    # POST - proposal-aware Model field editing
    # =================================================================

    if request.method == "POST":

        field_name = request.POST.get(
            "field",
            "",
        ).strip()

        action = request.POST.get(
            "action",
            "",
        ).strip()

        value = request.POST.get(
            "value",
            "",
        )

        if field_name not in EDITABLE_FIELDS:

            return JsonResponse(
                {
                    "success": False,
                    "error": "Invalid field.",
                },
                status=400,
            )

        # =============================================================
        # DISCARD
        # =============================================================

        if action == "discard":

            if proposal is None:

                return JsonResponse(
                    {
                        "success": False,
                        "error": "No working proposal exists.",
                    },
                    status=400,
                )

            ProposalService.discard_change(
                proposal=proposal,
                target_type="Model",
                target_id=model.id,
                field=field_name,
            )

            return JsonResponse(
                {
                    "success": True,
                    "field": field_name,
                    "value": getattr(
                        model,
                        field_name,
                    ),
                    "proposed": False,
                }
            )

        # =============================================================
        # SAVE
        # =============================================================

        if action:

            return JsonResponse(
                {
                    "success": False,
                    "error": "Invalid action.",
                },
                status=400,
            )

        validation_error = _validate_model_field(
            field_name,
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

        canonical_value = getattr(
            model,
            field_name,
        )

        # -------------------------------------------------------------
        # Saving the canonical value means there is no proposal to
        # maintain for this field. Discard the existing change.
        # -------------------------------------------------------------

        if value == canonical_value:

            if proposal:

                ProposalService.discard_change(
                    proposal=proposal,
                    target_type="Model",
                    target_id=model.id,
                    field=field_name,
                )

            return JsonResponse(
                {
                    "success": True,
                    "field": field_name,
                    "value": canonical_value,
                    "proposed": False,
                }
            )

        # -------------------------------------------------------------
        # Create/retrieve the user's active proposal.
        # -------------------------------------------------------------

        proposal, error_response = get_or_create_active_proposal(
            request,
            model,
            request.user,
        )

        if error_response is not None:
            return error_response

        change = ProposalService.record_change(
            proposal=proposal,
            operation=ProposalChange.Operation.UPDATE,
            target_type="Model",
            target_id=model.id,
            parent_type="",
            parent_id=None,
            field=field_name,
            before={
                "field": field_name,
                "value": canonical_value,
            },
            after={
                "field": field_name,
                "value": value,
            },
        )

        return JsonResponse(
            {
                "success": True,
                "proposal_id": str(
                    proposal.id,
                ),
                "change_id": str(
                    change.id,
                ),
                "field": field_name,
                "value": value,
                "proposed": True,
            }
        )

    # =================================================================
    # GET - working Model values
    # =================================================================

    working_values, proposed_fields = _get_working_model_values(
        model,
        proposal,
    )

    ontology_payload = compile_ontology_graph(
        model,
        proposal,
    ).to_dict()

    context.update(
        {
            "ontology_payload": ontology_payload,
            "ontology_legend": AppearanceService.legend(model),
            "canvas_background": AppearanceService.resolve_theme(model).canvas_background,
            "name_value": working_values["name"],
            "name_proposed": ("name" in proposed_fields),
            "description_value": working_values["description"],
            "description_proposed": ("description" in proposed_fields),
            "purpose_value": working_values["purpose"],
            "purpose_proposed": ("purpose" in proposed_fields),
            "scope_value": working_values["scope"],
            "scope_proposed": ("scope" in proposed_fields),
            "exclusions_value": working_values["exclusions"],
            "exclusions_proposed": ("exclusions" in proposed_fields),
            "publications_count": model.publications.count(),
        }
    )

    return render(
        request,
        "model/overview.html",
        context,
    )
