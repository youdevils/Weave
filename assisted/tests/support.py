"""Shared fixtures for assisted app tests."""

import io

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


def build_minimal_pdf(text: str) -> bytes:
    """
    Assembles a minimal, structurally valid one-page PDF containing `text`,
    computing real xref offsets from the bytes actually written instead of
    hand-typing them (hand-typed offsets drift the moment the surrounding
    content changes and are a classic source of flaky PDF fixtures).
    `text` must not contain PDF string-literal special characters ( ) \\.
    """

    buf = io.BytesIO()
    offsets = {}

    def write(chunk: bytes):
        buf.write(chunk)

    def obj(n, body: bytes):
        offsets[n] = buf.tell()
        write(f"{n} 0 obj\n".encode())
        write(body)
        write(b"\nendobj\n")

    write(b"%PDF-1.4\n")
    obj(1, b"<< /Type /Catalog /Pages 2 0 R >>")
    obj(2, b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>")
    obj(
        3,
        b"<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 4 0 R >> >> "
        b"/MediaBox [0 0 300 300] /Contents 5 0 R >>",
    )
    obj(4, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    content_stream = f"BT /F1 18 Tf 20 150 Td ({text}) Tj ET".encode("latin-1")
    obj(5, f"<< /Length {len(content_stream)} >>\nstream\n".encode() + content_stream + b"\nendstream")

    xref_offset = buf.tell()
    write(b"xref\n")
    write(f"0 {len(offsets) + 1}\n".encode())
    write(b"0000000000 65535 f \n")
    for n in sorted(offsets):
        write(f"{offsets[n]:010d} 00000 n \n".encode())

    write(b"trailer\n")
    write(f"<< /Size {len(offsets) + 1} /Root 1 0 R >>\n".encode())
    write(b"startxref\n")
    write(f"{xref_offset}\n".encode())
    write(b"%%EOF")

    return buf.getvalue()


def build_minimal_docx(text: str) -> bytes:
    from docx import Document

    document = Document()
    document.add_paragraph(text)
    buf = io.BytesIO()
    document.save(buf)
    return buf.getvalue()


class AssistedTestCase(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.workspace = Workspace.objects.create(name="Test Workspace")

        cls.owner = CustomUser.objects.create_user(email="owner@example.com", password="pw")
        cls.editor = CustomUser.objects.create_user(email="editor@example.com", password="pw")
        cls.other_editor = CustomUser.objects.create_user(email="editor2@example.com", password="pw")
        cls.viewer = CustomUser.objects.create_user(email="viewer@example.com", password="pw")
        cls.stranger = CustomUser.objects.create_user(email="stranger@example.com", password="pw")

        # These are the users every non-entitlement test in this app expects
        # to be able to actually run Assisted operations -- entitlement is a
        # separate concern from role, covered on its own in
        # assisted.tests.test_lifecycle / test_execution.
        for user in (cls.owner, cls.editor, cls.other_editor):
            user.plan = CustomUser.Plan.COLLABORATOR
            user.save(update_fields=["plan"])

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
