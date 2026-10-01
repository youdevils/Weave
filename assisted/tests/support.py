"""Shared fixtures for assisted app tests."""

from django.test import TestCase

from account.models import CustomUser
from model.models.model import Model
from model.models.object_type import ObjectType
from workspace.models import Workspace, WorkspaceMember

from ai.services.change_plan import ChangeAction, ChangePlan, EntityRef
from ai.services.result_schema import (
    AIStructuredResult,
    Interpretation,
    UnresolvedIssue,
)

# Re-exported so test modules only need one import line.
from ai.tests.support import RaisingProvider, ScriptedProvider  # noqa: F401


def _new(token):
    return EntityRef(kind="new", id=token)


def _existing(id_):
    return EntityRef(kind="existing", id=str(id_))


def clarification_result():
    return AIStructuredResult(needs_clarification=True, clarification_question="Which widget?")


def no_change_result():
    return AIStructuredResult(interpretation=Interpretation(restated_intent="Nothing to do."))


def unresolved_result():
    return AIStructuredResult(
        unresolved_issues=[UnresolvedIssue(code="ambiguous", message="Too ambiguous to act on.")],
    )


def create_object_plan(object_type_id, name="New widget", token="tmp:1"):
    return AIStructuredResult(
        interpretation=Interpretation(restated_intent="Create a widget."),
        change_plan=ChangePlan(
            summary="Create a widget.",
            actions=[
                ChangeAction(
                    operation="create",
                    target_type="Object",
                    target_ref=_new(token),
                    parent_ref=_existing(object_type_id),
                    fields={"name": name},
                )
            ],
        ),
    )


class AssistedTestCase(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.workspace = Workspace.objects.create(name="Test Workspace")

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

    def make_model(self, **kwargs):
        kwargs.setdefault("name", "Test Model")
        return Model.objects.create(workspace=self.workspace, **kwargs)

    def make_object_type(self, model, key="widget", name=None):
        return ObjectType.objects.create(model=model, key=key, name=name or key.title())
