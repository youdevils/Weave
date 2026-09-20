import logging

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from model.models.model import Model
from model.models.proposal import Proposal, ProposalChange
from model.models.proposal_submission_result import (
    ProposalSubmissionResult,
    ProposalValidationError,
)
from model.services.appearance import AppearanceService
from model.services.proposal.review import ProposalReviewService
from model.services.validation.fields import (
    validate_object_builtin_fields,
    validate_object_field,
    validate_relationship_builtin_fields,
    validate_relationship_field,
)
from model.services.validation.model_validation import validate_model
from model.services.validation.result import ValidationIssue
from model.services.field_paths import ATTRIBUTE_FIELD_PREFIX

logger = logging.getLogger(__name__)

MODEL_MAP = ProposalReviewService.MODEL_MAP

# Fixed, hardcoded apply order across the known target types -- not a
# generic dependency engine. Derived directly from the FK graph:
# Object.object_type and Relationship.relationship_type are the only
# PROTECT foreign keys in the schema, so deletes must remove the
# referencing row before the referenced one.
_CREATE_UPDATE_ORDER = (
    "ObjectType",
    "RelationshipType",
    "AttributeDefinition",
    "RelationshipTypeRule",
    "Object",
    "Relationship",
)
_DELETE_ORDER = tuple(reversed(_CREATE_UPDATE_ORDER))

# Types whose (model, key) must be unique.
_KEY_UNIQUE_TYPES = ("ObjectType", "RelationshipType")

# Types whose instance attribute values live in a nested `attributes`
# JSON blob and are addressed by "attributes.<key>" field paths.
_ATTRIBUTE_HOST_TYPES = ("Object", "Relationship")


class _ValidationFailed(Exception):
    """
    Internal sentinel used to unwind the apply/validate transaction
    without persisting any of its speculative writes. Caught one
    level up in process(); never allowed to escape this module.
    """

    def __init__(self, issues, before_revision):
        super().__init__("Proposal validation failed")
        self.issues = issues
        self.before_revision = before_revision


# =========================================================================
# CREATE kwargs mapping
#
# Not a uniform dict-spread: verified against the real editor call
# sites, the five creatable types disagree on whether their parent's
# FK id lives in `after` (RelationshipTypeRule, Relationship do; the
# others don't -- it's carried only in parent_type/parent_id) and on
# whether `model_id` appears in `after` at all (never -- it always
# comes from the Model already in scope during processing).
# =========================================================================


def _create_kwargs(change, model):
    after = dict(change.after or {})

    if change.target_type in ("ObjectType", "RelationshipType"):
        return {"model_id": model.id, **after}

    if change.target_type == "AttributeDefinition":
        return {
            "object_type_id": (
                change.parent_id if change.parent_type == "ObjectType" else None
            ),
            "relationship_type_id": (
                change.parent_id if change.parent_type == "RelationshipType" else None
            ),
            **after,
        }

    if change.target_type == "Object":
        return {
            "model_id": model.id,
            "object_type_id": change.parent_id,
            **after,
        }

    if change.target_type == "RelationshipTypeRule":
        return {
            "relationship_type_id": change.parent_id,
            **after,
        }

    if change.target_type == "Relationship":
        return {
            "model_id": model.id,
            "relationship_type_id": change.parent_id,
            **after,
        }

    raise ValueError(f"Unsupported target_type for CREATE: {change.target_type}")


# =========================================================================
# Pre-checks (run BEFORE issuing a write, never left to raise a DB
# exception mid-transaction -- an IntegrityError/ProtectedError would
# abort the whole Postgres transaction, making it impossible to
# collect further errors).
# =========================================================================


def _duplicate_key_issue(target_type, model, target_id, key):
    if key is None:
        return None

    model_cls = MODEL_MAP[target_type]

    collision = (
        model_cls.objects.filter(model=model, key=key).exclude(id=target_id).exists()
    )

    if not collision:
        return None

    return ValidationIssue(
        code="duplicate_key",
        field="key",
        message=f"'{key}' is already in use.",
        target_type=target_type,
        target_id=target_id,
    )


def _duplicate_rule_issue(target_id, relationship_type_id, subject_type_id, object_type_id):
    from model.models.relationship_type_rule import RelationshipTypeRule

    if not (relationship_type_id and subject_type_id and object_type_id):
        return None

    collision = (
        RelationshipTypeRule.objects.filter(
            relationship_type_id=relationship_type_id,
            subject_type_id=subject_type_id,
            object_type_id=object_type_id,
        )
        .exclude(id=target_id)
        .exists()
    )

    if not collision:
        return None

    return ValidationIssue(
        code="duplicate_rule",
        message="A rule already exists for this subject/object type pair.",
        target_type="RelationshipTypeRule",
        target_id=target_id,
    )


def _attributed(issue, target_type, target_id):
    issue.target_type = target_type
    issue.target_id = target_id
    return issue


def _create_field_issues(model, change, target_type, kwargs):
    """
    Pre-check of a CREATE's built-in field values and, for a Relationship,
    of its endpoints -- reported as issues instead of being left to raise a
    database error mid-apply. The rules themselves live in
    model.services.validation.fields; a value missing from the payload takes
    the model default, exactly as the write below would.
    """

    if target_type == "Object":
        issues = validate_object_builtin_fields(
            name=kwargs.get("name", ""),
            description=kwargs.get("description", ""),
            is_active=kwargs.get("is_active", True),
        )

    elif target_type == "Relationship":
        issues = validate_relationship_builtin_fields(
            is_active=kwargs.get("is_active", True),
        )

        for field in ("subject_id", "object_id"):
            if not _object_exists_in_model(model, kwargs.get(field)):
                issues.append(
                    ValidationIssue(
                        code="endpoint_not_found",
                        field=field,
                        message=(
                            f"The {'subject' if field == 'subject_id' else 'object'} "
                            "of this relationship no longer exists in this model."
                        ),
                    )
                )

    else:
        return []

    return [_attributed(issue, target_type, change.target_id) for issue in issues]


def _object_exists_in_model(model, object_id):
    from model.models.object import Object

    if not object_id:
        return False

    try:
        return Object.objects.filter(model=model, id=object_id).exists()
    except (ValueError, TypeError, ValidationError):
        return False


def _protected_delete_issue(target_type, target_id, proposal_deleted_ids):
    if target_type == "ObjectType":
        from model.models.object import Object

        referencing = Object.objects.filter(object_type_id=target_id).exclude(
            id__in=proposal_deleted_ids.get("Object", set())
        )
        code = "protected_reference"
        message = (
            "This object type still has objects and cannot be deleted."
        )

    elif target_type == "RelationshipType":
        from model.models.relationship import Relationship

        referencing = Relationship.objects.filter(relationship_type_id=target_id).exclude(
            id__in=proposal_deleted_ids.get("Relationship", set())
        )
        code = "protected_reference"
        message = (
            "This relationship type still has relationships and cannot be deleted."
        )

    else:
        return None

    if not referencing.exists():
        return None

    return ValidationIssue(
        code=code,
        message=message,
        target_type=target_type,
        target_id=target_id,
    )


# =========================================================================
# Apply
# =========================================================================


def _apply_model_field_update(model, change, issues, model_fields_changed):
    after = change.after or {}
    field = after.get("field")

    if not field or not hasattr(model, field):
        issues.append(
            ValidationIssue(
                code="invalid_change",
                message=f"Unrecognised Model field '{field}'.",
                target_type="Model",
                target_id=change.target_id,
            )
        )
        return

    setattr(model, field, after.get("value"))
    model_fields_changed.add(field)


def _apply_attribute_update(instance, change, target_type, issues):
    """
    Apply an "attributes.<key>" UPDATE by replacing that one key inside the
    instance's `attributes` JSON, leaving every other key untouched. Mirrors
    the overlay in model.views.data_context.apply_field_updates: the value
    (including None) is stored as-is and the key is never removed.

    Only checks that the key is defined for the instance's type; whether the
    value is acceptable stays with validate_model. Problems are reported as
    issues and skip the write, so nothing is partially applied.
    """

    after = change.after or {}
    key = after["field"][len(ATTRIBUTE_FIELD_PREFIX):]

    def issue(code, message, field=None):
        issues.append(
            ValidationIssue(
                code=code,
                field=field,
                message=message,
                target_type=target_type,
                target_id=change.target_id,
            )
        )

    if not key:
        issue("invalid_change", f"Unrecognised {target_type} field '{after['field']}'.")
        return

    if "value" not in after:
        issue("invalid_change", f"No value given for attribute '{key}'.", field=key)
        return

    if target_type == "Object":
        definitions = instance.object_type.attribute_definitions
    else:
        definitions = instance.relationship_type.relationship_definitions

    if not definitions.filter(key=key).exists():
        issue(
            "unknown_attribute",
            f"Attribute '{key}' is not defined for this type.",
            field=key,
        )
        return

    current = instance.attributes if instance.attributes is not None else {}

    if not isinstance(current, dict):
        issue(
            "invalid_change",
            f"{target_type} attributes are not a JSON object.",
            field=key,
        )
        return

    instance.attributes = {**current, key: after["value"]}
    instance.save(update_fields=["attributes", "updated_at"])


def _apply_create_or_update(model, change, target_type, issues, proposal_deleted_ids):
    model_cls = MODEL_MAP[target_type]

    if change.operation == ProposalChange.Operation.CREATE:
        kwargs = _create_kwargs(change, model)

        if target_type in _KEY_UNIQUE_TYPES:
            duplicate = _duplicate_key_issue(
                target_type, model, change.target_id, kwargs.get("key")
            )
            if duplicate:
                issues.append(duplicate)
                return

        if target_type == "RelationshipTypeRule":
            duplicate = _duplicate_rule_issue(
                change.target_id,
                kwargs.get("relationship_type_id"),
                kwargs.get("subject_type_id"),
                kwargs.get("object_type_id"),
            )
            if duplicate:
                issues.append(duplicate)
                return

        field_issues = _create_field_issues(model, change, target_type, kwargs)
        if field_issues:
            issues.extend(field_issues)
            return

        model_cls.objects.create(id=change.target_id, **kwargs)
        return

    # UPDATE (field-level)
    instance = model_cls.objects.filter(id=change.target_id).first()

    if instance is None:
        issues.append(
            ValidationIssue(
                code="target_not_found",
                message=f"{target_type} no longer exists.",
                target_type=target_type,
                target_id=change.target_id,
            )
        )
        return

    after = change.after or {}
    field = after.get("field")

    if (
        target_type in _ATTRIBUTE_HOST_TYPES
        and isinstance(field, str)
        and field.startswith(ATTRIBUTE_FIELD_PREFIX)
    ):
        _apply_attribute_update(instance, change, target_type, issues)
        return

    if not field or not hasattr(instance, field):
        issues.append(
            ValidationIssue(
                code="invalid_change",
                message=f"Unrecognised {target_type} field '{field}'.",
                target_type=target_type,
                target_id=change.target_id,
            )
        )
        return

    if target_type == "Object":
        field_issue = validate_object_field(field, after.get("value"))
    elif target_type == "Relationship":
        field_issue = validate_relationship_field(field, after.get("value"))
    else:
        field_issue = None

    if field_issue is not None:
        issues.append(_attributed(field_issue, target_type, change.target_id))
        return

    setattr(instance, field, after.get("value"))

    if target_type in _KEY_UNIQUE_TYPES and field == "key":
        duplicate = _duplicate_key_issue(
            target_type, model, change.target_id, instance.key
        )
        if duplicate:
            issues.append(duplicate)
            return

    if target_type == "RelationshipTypeRule" and field in (
        "subject_type_id",
        "object_type_id",
    ):
        duplicate = _duplicate_rule_issue(
            change.target_id,
            instance.relationship_type_id,
            instance.subject_type_id,
            instance.object_type_id,
        )
        if duplicate:
            issues.append(duplicate)
            return

    instance.save(update_fields=[field, "updated_at"])


def _apply_delete(change, target_type, issues, proposal_deleted_ids):
    model_cls = MODEL_MAP[target_type]

    protection_issue = _protected_delete_issue(
        target_type, change.target_id, proposal_deleted_ids
    )

    if protection_issue:
        issues.append(protection_issue)
        return

    deleted, _ = model_cls.objects.filter(id=change.target_id).delete()

    if deleted:
        proposal_deleted_ids.setdefault(target_type, set()).add(change.target_id)


def _apply_changes(model, proposal):
    """
    Apply every change in the proposal against canonical tables, still
    inside the caller's open transaction (nothing committed yet).
    Returns the list of ValidationIssues produced by pre-checks (a
    skipped write due to a duplicate key / protected reference is
    reported as an issue, never as a raised DB exception, so the rest
    of the pass -- and full validation afterward -- can still run).

    Known limitation (accepted, not a generic dependency engine): all
    CREATE/UPDATEs across every type apply before any DELETEs, so a
    proposal that deletes something and creates a replacement reusing
    the same unique key in the same submission is not supported --
    sophisticated same-proposal conflict resolution is out of scope.
    """

    issues: list[ValidationIssue] = []
    model_fields_changed: set[str] = set()
    proposal_deleted_ids: dict[str, set] = {}

    by_type: dict[str, list[ProposalChange]] = {}
    for change in proposal.changes.all():
        by_type.setdefault(change.target_type, []).append(change)

    for change in by_type.get("Model", []):
        if change.operation == ProposalChange.Operation.UPDATE:
            _apply_model_field_update(model, change, issues, model_fields_changed)

    for target_type in _CREATE_UPDATE_ORDER:
        for change in by_type.get(target_type, []):
            if change.operation in (
                ProposalChange.Operation.CREATE,
                ProposalChange.Operation.UPDATE,
            ):
                _apply_create_or_update(
                    model, change, target_type, issues, proposal_deleted_ids
                )

    for target_type in _DELETE_ORDER:
        for change in by_type.get(target_type, []):
            if change.operation == ProposalChange.Operation.DELETE:
                _apply_delete(change, target_type, issues, proposal_deleted_ids)

    if model_fields_changed:
        model.save(update_fields=[*model_fields_changed, "updated_at"])

    return issues


# =========================================================================
# Error attribution
# =========================================================================


def _index_changes_by_target(proposal):
    by_target: dict[tuple, list[ProposalChange]] = {}

    for change in proposal.changes.all():
        by_target.setdefault((change.target_type, change.target_id), []).append(change)

    return by_target


def _match_change(issue, by_target):
    if not issue.target_type or not issue.target_id:
        return None

    candidates = by_target.get((issue.target_type, issue.target_id))

    if not candidates:
        return None

    if len(candidates) == 1:
        return candidates[0]

    if issue.field:
        # Attribute issues carry the bare attribute key, while the change
        # addresses it as "attributes.<key>".
        wanted = [issue.field]
        if issue.target_type in _ATTRIBUTE_HOST_TYPES:
            wanted.insert(0, f"{ATTRIBUTE_FIELD_PREFIX}{issue.field}")

        for field in wanted:
            for change in candidates:
                after = change.after or {}
                if after.get("field") == field:
                    return change

    for change in candidates:
        if change.operation in (
            ProposalChange.Operation.CREATE,
            ProposalChange.Operation.DELETE,
        ):
            return change

    return candidates[0]


def _store_result(
    proposal,
    *,
    outcome,
    before_revision=None,
    after_revision=None,
    message="",
    issues=None,
):
    result, _ = ProposalSubmissionResult.objects.update_or_create(
        proposal=proposal,
        defaults={
            "outcome": outcome,
            "before_revision": before_revision,
            "after_revision": after_revision,
            "message": message,
        },
    )

    result.errors.all().delete()

    if issues:
        by_target = _index_changes_by_target(proposal)

        ProposalValidationError.objects.bulk_create(
            [
                ProposalValidationError(
                    result=result,
                    change=_match_change(issue, by_target),
                    code=issue.code,
                    message=issue.message,
                    target_type=issue.target_type or "",
                    target_id=issue.target_id,
                    field=issue.field or "",
                )
                for issue in issues
            ]
        )

    return result


# =========================================================================
# Queue: claim + process
# =========================================================================


def claim_next(model_id):
    """
    Txn 1 -- cheap, fast. Claims the next QUEUED proposal for this
    Model (FIFO by submitted_at), or reclaims a PROCESSING one whose
    worker apparently died (stale beyond PROPOSAL_PROCESSING_STUCK_THRESHOLD).
    Returns the claimed Proposal, or None if there is nothing to do or
    something is already genuinely processing.
    """

    with transaction.atomic():
        model = Model.objects.select_for_update().filter(id=model_id).first()

        if model is None:
            # Deleted since this task was dispatched.
            return None

        cutoff = timezone.now() - settings.PROPOSAL_PROCESSING_STUCK_THRESHOLD

        active_processing = Proposal.objects.filter(
            model=model,
            status=Proposal.Status.PROCESSING,
            updated_at__gte=cutoff,
        ).exists()

        if active_processing:
            return None

        proposal = (
            Proposal.objects.select_for_update()
            .filter(model=model)
            .filter(
                Q(status=Proposal.Status.QUEUED)
                | Q(status=Proposal.Status.PROCESSING, updated_at__lt=cutoff)
            )
            .order_by("submitted_at", "id")
            .first()
        )

        if proposal is None:
            return None

        proposal.status = Proposal.Status.PROCESSING
        proposal.save(update_fields=["status", "updated_at"])

    def _dispatch():
        from model.tasks.proposal_tasks import process_proposal

        process_proposal.delay(str(proposal.id))

    transaction.on_commit(_dispatch)

    return proposal


def process(proposal_id):
    """
    Txn 2 -- the heavy phase: apply, validate, commit-or-fail. Locks
    the Model row for its duration, which is what actually serializes
    per-model processing end-to-end (a concurrent claim_next() for the
    same model blocks here until this commits or rolls back).
    """

    model_id = (
        Proposal.objects.filter(id=proposal_id)
        .values_list("model_id", flat=True)
        .first()
    )

    if model_id is None:
        # Its model was deleted since this task was dispatched.
        return

    def _dispatch_next():
        from model.tasks.proposal_tasks import process_next_for_model

        process_next_for_model.delay(str(model_id))

    try:
        with transaction.atomic():
            proposal = Proposal.objects.select_for_update().get(id=proposal_id)

            if proposal.status != Proposal.Status.PROCESSING:
                # Already handled by a racing/redelivered task.
                return

            model = Model.objects.select_for_update().get(id=proposal.model_id)
            before_revision = model.revision

            apply_issues = _apply_changes(model, proposal)
            result = validate_model(model)
            issues = apply_issues + result.issues

            if issues:
                raise _ValidationFailed(issues, before_revision)

            model.revision = before_revision + 1
            model.save(update_fields=["revision", "updated_at"])

            proposal.status = Proposal.Status.COMPLETED
            proposal.validation_status = Proposal.ValidationStatus.VALID
            proposal.completed_at = timezone.now()
            proposal.save(
                update_fields=[
                    "status",
                    "validation_status",
                    "completed_at",
                    "updated_at",
                ]
            )

            # Types deleted by this proposal no longer need their style; types it
            # created keep theirs (same UUID, now canonical).
            AppearanceService.prune(model)

            _store_result(
                proposal,
                outcome=ProposalSubmissionResult.Outcome.SUCCESS,
                before_revision=before_revision,
                after_revision=model.revision,
            )

            # Registered from INSIDE this transaction: only fires once
            # this specific commit actually lands. If anything above
            # raises, this line never runs and the queue is not
            # advanced.
            transaction.on_commit(_dispatch_next)

    except _ValidationFailed as failure:
        with transaction.atomic():
            proposal = Proposal.objects.select_for_update().get(id=proposal_id)
            proposal.status = Proposal.Status.FAILED
            proposal.validation_status = Proposal.ValidationStatus.INVALID
            proposal.save(update_fields=["status", "validation_status", "updated_at"])

            _store_result(
                proposal,
                outcome=ProposalSubmissionResult.Outcome.VALIDATION_FAILED,
                before_revision=failure.before_revision,
                issues=failure.issues,
            )

            transaction.on_commit(_dispatch_next)

    except Exception:
        logger.exception("Unexpected error processing proposal %s", proposal_id)

        with transaction.atomic():
            proposal = Proposal.objects.select_for_update().get(id=proposal_id)
            proposal.status = Proposal.Status.FAILED
            proposal.save(update_fields=["status", "updated_at"])

            _store_result(
                proposal,
                outcome=ProposalSubmissionResult.Outcome.SYSTEM_ERROR,
                message="An unexpected error occurred while processing this proposal.",
            )

            transaction.on_commit(_dispatch_next)
