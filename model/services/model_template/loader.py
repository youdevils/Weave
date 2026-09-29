from django.db import transaction

from model.models.proposal import Proposal
from model.models.proposal_submission_result import ProposalValidationError
from model.services.appearance import AppearanceService, OBJECT_TYPE, RELATIONSHIP_TYPE
from model.services.proposal import submission
from model.services.proposal.proposal import ProposalService

from model.model_templates.business_process import (
    BUSINESS_PROCESS_TEMPLATE,
)

from model.model_templates.delivery_project import (
    DELIVERY_PROJECT_TEMPLATE,
)

from model.model_templates.new_zealand_farm_operations import (
    NEW_ZEALAND_FARM_OPERATIONS_TEMPLATE,
)

from .builder import TemplateDefinitionError, build_template_changes

TEMPLATES = {
    BUSINESS_PROCESS_TEMPLATE["key"]: BUSINESS_PROCESS_TEMPLATE,
    DELIVERY_PROJECT_TEMPLATE["key"]: DELIVERY_PROJECT_TEMPLATE,
    NEW_ZEALAND_FARM_OPERATIONS_TEMPLATE["key"]: NEW_ZEALAND_FARM_OPERATIONS_TEMPLATE,
}


def get_template(key: str) -> dict:
    """
    Return a model template by its stable key.
    """

    try:
        return TEMPLATES[key]
    except KeyError:
        raise ValueError(f"Unknown model template: '{key}'.")


def template_has_data(template: dict) -> bool:
    """Whether this template ships populated sample data, not just structure."""

    return bool(template.get("objects"))


class TemplateInstantiationFailure(Exception):
    """The template did not validate; nothing from the attempt was persisted."""

    def __init__(self, message, issues=None):
        super().__init__(message)
        self.issues = issues or []


@transaction.atomic
def instantiate_template_via_proposal(model, template_key: str, user):
    """
    Populate `model` from `template_key` through the normal proposal
    lifecycle: create a working proposal, record every object type /
    attribute / relationship type / attribute / rule / object / relationship
    the template defines as a ProposalChange, submit it, and process it
    synchronously (the same claim_next()/process() pair the Celery worker
    runs, invoked inline instead of dispatched) so validate_model() runs
    against the complete proposed model before anything becomes canonical.

    Once the proposal has completed, any template-defined initial
    appearance is applied via AppearanceService, using the same type ids
    the proposal just made canonical.

    Raises TemplateDefinitionError if the template dict itself is malformed
    (duplicate/unknown template-local keys), or TemplateInstantiationFailure
    if the complete proposed model does not validate. Both are raised from
    inside this function's transaction, so nothing it did -- proposal,
    changes, canonical rows, appearance -- survives either failure.
    """

    template = get_template(template_key)

    proposal = ProposalService.create_working(
        model,
        user,
        title=f"Initialise from {template['name']} template"[:200],
        summary=f"Create initial model from {template['name']} template",
    )

    change_set = build_template_changes(template, model.id)

    ProposalService.record_changes_bulk(
        proposal=proposal,
        specs=change_set.specs,
    )

    ProposalService.submit(proposal)

    # This model has exactly one live proposal at this point (the one just
    # created), so claiming and processing it inline is deterministic --
    # there is nothing else for claim_next() to have picked instead.
    claimed = submission.claim_next(model.id)
    submission.process(claimed.id)

    proposal.refresh_from_db()

    if proposal.status != Proposal.Status.COMPLETED:
        issues = list(ProposalValidationError.objects.filter(result__proposal=proposal))
        raise TemplateInstantiationFailure(
            f"Template '{template_key}' failed validation.",
            issues,
        )

    apply_template_appearance(model, template, change_set)

    return model


def apply_template_appearance(model, template, change_set):
    """
    Write a template's declared initial appearance into Model.appearance,
    resolving template-local object-type/relationship-type keys through the
    ids build_template_changes() already generated for them (now canonical).
    """

    appearance = template.get("appearance", {})

    for key, style in appearance.get("object_types", {}).items():
        try:
            type_id = change_set.object_type_ids[key]
        except KeyError:
            raise TemplateDefinitionError(
                f"Template appearance references unknown object type '{key}'."
            ) from None

        for field, value in style.items():
            AppearanceService.set_type_style(model, OBJECT_TYPE, type_id, field, value)

    for key, style in appearance.get("relationship_types", {}).items():
        try:
            type_id = change_set.relationship_type_ids[key]
        except KeyError:
            raise TemplateDefinitionError(
                f"Template appearance references unknown relationship type '{key}'."
            ) from None

        for field, value in style.items():
            AppearanceService.set_type_style(
                model, RELATIONSHIP_TYPE, type_id, field, value
            )
