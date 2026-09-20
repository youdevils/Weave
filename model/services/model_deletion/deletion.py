from django.db import transaction
from django.db.models import Q

from model.models.attribute_definition import AttributeDefinition
from model.models.model import Model
from model.models.object import Object
from model.models.object_type import ObjectType
from model.models.proposal import Proposal
from model.models.relationship import Relationship
from model.models.relationship_type import RelationshipType
from model.models.relationship_type_rule import RelationshipTypeRule


class ModelDeletionBlocked(Exception):
    """The model cannot be deleted right now; the message is user-facing."""


# Statuses owned by the background proposal queue. A worker may be about to
# claim, or be in the middle of applying, a proposal in either of these.
_IN_FLIGHT_STATUSES = (
    Proposal.Status.QUEUED,
    Proposal.Status.PROCESSING,
)


def delete_model(model):
    """
    Hard-delete a Model and everything it owns.

    Deleted in dependency order, referencing rows before the rows they
    reference: Object.object_type and Relationship.relationship_type are
    PROTECT foreign keys, so objects and relationships must go before their
    types. Deleting the proposals cascades to their changes, evidence
    references and submission results (none of which have a foreign key to
    the Model itself).

    The Model row is locked first -- the same lock proposal claiming and
    processing take -- so this serialises with a worker in flight. A proposal
    that is QUEUED or PROCESSING blocks deletion: there is no way to cancel
    one, and a worker must never keep operating on a deleted model.
    """

    with transaction.atomic():
        locked = Model.objects.select_for_update().get(pk=model.pk)

        if Proposal.objects.filter(
            model=locked,
            status__in=_IN_FLIGHT_STATUSES,
        ).exists():
            raise ModelDeletionBlocked(
                "This model has a proposal that is queued or being "
                "processed. Wait for it to finish, then try again."
            )

        Relationship.objects.filter(model=locked).delete()
        Object.objects.filter(model=locked).delete()

        RelationshipTypeRule.objects.filter(
            Q(relationship_type__model=locked)
            | Q(subject_type__model=locked)
            | Q(object_type__model=locked)
        ).delete()
        AttributeDefinition.objects.filter(
            Q(object_type__model=locked) | Q(relationship_type__model=locked)
        ).delete()

        RelationshipType.objects.filter(model=locked).delete()
        ObjectType.objects.filter(model=locked).delete()

        Proposal.objects.filter(model=locked).delete()

        locked.delete()
