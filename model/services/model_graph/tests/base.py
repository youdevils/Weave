import uuid

from django.test import TestCase

from account.models import CustomUser
from model.models.attribute_definition import AttributeDefinition
from model.models.model import Model
from model.models.object import Object
from model.models.object_type import ObjectType
from model.models.proposal import Proposal, ProposalChange
from model.models.relationship import Relationship
from model.models.relationship_type import RelationshipType
from model.models.relationship_type_rule import RelationshipTypeRule
from model.services import keys
from workspace.models import Workspace

Op = ProposalChange.Operation


class ModelGraphTestCase(TestCase):
    """Shared fixture: Person/Team object types with one relationship type."""

    @classmethod
    def setUpTestData(cls):
        cls.workspace = Workspace.objects.create(name="Test Workspace")
        cls.user = CustomUser.objects.create_user(email="user@example.com", password="test-password")
        cls.model = Model.objects.create(workspace=cls.workspace, name="Test Model", revision=1)

    def setUp(self):
        self.person_type = ObjectType.objects.create(model=self.model, name="Person", key="person", is_active=True)
        self.team_type = ObjectType.objects.create(model=self.model, name="Team", key="team", is_active=True)
        self.member_of = RelationshipType.objects.create(
            model=self.model, name="Member of", key="member_of", is_active=True
        )
        RelationshipTypeRule.objects.create(
            relationship_type=self.member_of, subject_type=self.person_type, object_type=self.team_type
        )
        self.status_attribute = AttributeDefinition.objects.create(
            object_type=self.person_type,
            name="Status",
            key="status",
            data_type=AttributeDefinition.DataType.CHOICE,
            config={"choices": ["Active", "Left"]},
        )

    # -- builders ------------------------------------------------------------

    def make_object(self, object_type, name, **kwargs):
        kwargs.setdefault(
            "key",
            keys.generate_key("Object", name, model=self.model, parent_id=object_type.id),
        )
        return Object.objects.create(model=self.model, object_type=object_type, name=name, **kwargs)

    def make_relationship(self, subject, target, relationship_type=None, **kwargs):
        return Relationship.objects.create(
            model=self.model,
            relationship_type=relationship_type or self.member_of,
            subject=subject,
            object=target,
            **kwargs,
        )

    def working_proposal(self):
        return Proposal.objects.create(model=self.model, created_by=self.user, status=Proposal.Status.WORKING)

    def add_change(self, proposal, **kwargs):
        defaults = {"proposal": proposal, "source": ProposalChange.Source.USER}
        defaults.update(kwargs)
        return ProposalChange.objects.create(**defaults)

    def update(self, proposal, target_type, target_id, field, value):
        return self.add_change(
            proposal,
            operation=Op.UPDATE,
            target_type=target_type,
            target_id=target_id,
            after={"field": field, "value": value},
        )

    def propose_object(self, proposal, object_type_id, name, attributes=None, **after):
        object_id = uuid.uuid4()
        self.add_change(
            proposal,
            operation=Op.CREATE,
            target_type="Object",
            target_id=object_id,
            parent_type="ObjectType",
            parent_id=object_type_id,
            after={"name": name, "description": "", "is_active": True, "attributes": attributes or {}, **after},
        )
        return object_id

    def propose_relationship(self, proposal, subject_id, object_id, relationship_type=None, **after):
        relationship_id = uuid.uuid4()
        self.add_change(
            proposal,
            operation=Op.CREATE,
            target_type="Relationship",
            target_id=relationship_id,
            parent_type="RelationshipType",
            parent_id=(relationship_type or self.member_of).id,
            after={"subject_id": str(subject_id), "object_id": str(object_id), "is_active": True, "attributes": {}, **after},
        )
        return relationship_id
