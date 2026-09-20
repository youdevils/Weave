import csv
import io
import uuid

from django.test import TestCase

from account.models import CustomUser
from ingestion.models import ImportSource
from ingestion.services import source_file
from model.models.attribute_definition import AttributeDefinition
from model.models.model import Model
from model.models.object import Object
from model.models.object_type import ObjectType
from model.models.relationship import Relationship
from model.models.relationship_type import RelationshipType
from model.models.relationship_type_rule import RelationshipTypeRule
from workspace.models import Workspace, WorkspaceMember

DataType = AttributeDefinition.DataType


def csv_bytes(rows, *, bom=False):
    """rows: a list of lists, first row the header."""

    buffer = io.StringIO(newline="")
    csv.writer(buffer, lineterminator="\r\n").writerows(rows)
    data = buffer.getvalue().encode("utf-8")

    return (b"\xef\xbb\xbf" + data) if bom else data


class ImportTestCase(TestCase):
    """
    A model with an Application object type (external `app_id`, `owner`, `cost`,
    `live`, `tier` choice), a Person type, and a `uses` relationship type
    (Application -> Application) carrying a `since` attribute; plus workspace
    roles and a second workspace/model for isolation tests.
    """

    @classmethod
    def setUpTestData(cls):
        cls.workspace = Workspace.objects.create(name="Workspace")
        cls.model = Model.objects.create(workspace=cls.workspace, name="Model")

        cls.owner = CustomUser.objects.create_user(email="owner@example.com", password="pw")
        cls.editor = CustomUser.objects.create_user(email="editor@example.com", password="pw")
        cls.other_editor = CustomUser.objects.create_user(email="editor2@example.com", password="pw")
        cls.viewer = CustomUser.objects.create_user(email="viewer@example.com", password="pw")
        cls.stranger = CustomUser.objects.create_user(email="stranger@example.com", password="pw")

        for user, role in (
            (cls.owner, WorkspaceMember.Role.OWNER),
            (cls.editor, WorkspaceMember.Role.EDITOR),
            (cls.other_editor, WorkspaceMember.Role.EDITOR),
            (cls.viewer, WorkspaceMember.Role.VIEWER),
        ):
            WorkspaceMember.objects.create(workspace=cls.workspace, user=user, role=role)

        cls.other_workspace = Workspace.objects.create(name="Other Workspace")
        WorkspaceMember.objects.create(
            workspace=cls.other_workspace, user=cls.stranger, role=WorkspaceMember.Role.OWNER
        )
        cls.other_model = Model.objects.create(workspace=cls.other_workspace, name="Other")

        cls.app_type = ObjectType.objects.create(model=cls.model, name="Application", key="application")
        cls.person_type = ObjectType.objects.create(model=cls.model, name="Person", key="person")

        cls.app_id = cls.attribute(cls.app_type, "App ID", "app_id", DataType.TEXT)
        cls.owner_attr = cls.attribute(cls.app_type, "Owner", "owner", DataType.TEXT, nullable=True)
        cls.cost = cls.attribute(cls.app_type, "Cost", "cost", DataType.NUMBER, nullable=True)
        cls.live = cls.attribute(cls.app_type, "Live", "live", DataType.BOOLEAN, nullable=True)
        cls.go_live = cls.attribute(cls.app_type, "Go live", "go_live", DataType.DATE, nullable=True)
        cls.tier = cls.attribute(
            cls.app_type, "Tier", "tier", DataType.CHOICE, config={"choices": ["gold", "silver"]},
            nullable=True,
        )

        cls.uses = RelationshipType.objects.create(model=cls.model, name="Uses", key="uses")
        RelationshipTypeRule.objects.create(
            relationship_type=cls.uses, subject_type=cls.app_type, object_type=cls.app_type
        )
        cls.since = AttributeDefinition.objects.create(
            relationship_type=cls.uses, name="Since", key="since", data_type=DataType.DATE, nullable=True
        )

        cls.other_app_type = ObjectType.objects.create(model=cls.other_model, name="Application", key="application")

    @classmethod
    def attribute(cls, object_type, name, key, data_type, **extra):
        return AttributeDefinition.objects.create(
            object_type=object_type, name=name, key=key, data_type=data_type, **extra
        )

    # -- data helpers ---------------------------------------------------------

    def make_app(self, name, app_id=None, *, model=None, object_type=None, **attributes):
        attrs = dict(attributes)
        if app_id is not None:
            attrs["app_id"] = app_id
        return Object.objects.create(
            model=model or self.model,
            object_type=object_type or self.app_type,
            name=name,
            attributes=attrs,
        )

    def make_uses(self, subject, obj, **attributes):
        return Relationship.objects.create(
            model=self.model, relationship_type=self.uses, subject=subject, object=obj,
            attributes=attributes,
        )

    def stage(self, rows_or_bytes, filename="apps.csv", user=None):
        data = rows_or_bytes if isinstance(rows_or_bytes, bytes) else csv_bytes(rows_or_bytes)
        source, table = source_file.store_upload(self.model, user or self.editor, filename, data)
        return source

    # -- mappings -------------------------------------------------------------

    def object_mapping(self, *columns, type_id=None):
        return {
            "target": {"kind": "object", "type_id": str(type_id or self.app_type.id)},
            "columns": [dict(column) for column in columns],
        }

    def relationship_mapping(self, *columns):
        return {
            "target": {"kind": "relationship", "type_id": str(self.uses.id)},
            "columns": [dict(column) for column in columns],
        }

    def by_app_id(self, column, field):
        return {
            "column": column,
            "field": field,
            "by": "attribute:app_id",
            "object_type_id": str(self.app_type.id),
        }

    @staticmethod
    def new_id():
        return str(uuid.uuid4())
